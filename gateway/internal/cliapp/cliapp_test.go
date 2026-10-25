package cliapp

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/siddharthshankar/sutra/gateway/internal/audit"
	"github.com/siddharthshankar/sutra/gateway/internal/authcfg"
	"github.com/siddharthshankar/sutra/gateway/internal/confirm"
	"github.com/siddharthshankar/sutra/gateway/internal/gateway"
	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

// fixture spins up a real gateway (registry + auth + confirm + audit,
// wired the same way cmd/gateway's main() does) behind an httptest.Server,
// so these tests exercise cliapp.Run against the real MCP transport and
// gateway-core's real confirm-first flow — not a mock.
type fixture struct {
	ts          *httptest.Server
	mutateCalls *int32
}

const aliceToken = "alice-token"

func newFixture(t *testing.T) *fixture {
	t.Helper()

	mutateCalls := new(int32)
	reg := registry.New()
	reg.MustRegister(&registry.Definition{
		Name:        "echo",
		Tier:        registry.TierReadOnly,
		Description: "Echoes back the text argument.",
		Handler: func(ctx context.Context, userID string, args map[string]any) (any, error) {
			s, _ := args["text"].(string)
			return map[string]any{"echo": s}, nil
		},
	})
	reg.MustRegister(&registry.Definition{
		Name:        "mutate",
		Tier:        registry.TierConfirmFirst,
		Description: "A fake side-effecting action, gated by confirmation.",
		Describe: func(args map[string]any) string {
			s, _ := args["text"].(string)
			return "Mutate with text=" + s
		},
		Handler: func(ctx context.Context, userID string, args map[string]any) (any, error) {
			atomic.AddInt32(mutateCalls, 1)
			return map[string]any{"mutated": true}, nil
		},
	})

	tokensPath := filepath.Join(t.TempDir(), "tokens.yaml")
	if err := os.WriteFile(tokensPath, []byte(`
users:
  - id: alice
    token: `+aliceToken+`
    allowed_tools:
      - echo
      - mutate
`), 0o600); err != nil {
		t.Fatal(err)
	}
	authConfig, err := authcfg.Load(tokensPath)
	if err != nil {
		t.Fatalf("authcfg.Load: %v", err)
	}

	auditStore, err := audit.Open(filepath.Join(t.TempDir(), "audit.db"))
	if err != nil {
		t.Fatalf("audit.Open: %v", err)
	}
	t.Cleanup(func() { auditStore.Close() })

	confirmStore, err := confirm.Open(filepath.Join(t.TempDir(), "confirm.db"), time.Minute)
	if err != nil {
		t.Fatalf("confirm.Open: %v", err)
	}
	t.Cleanup(func() { confirmStore.Close() })

	server := gateway.NewMCPServer(gateway.Deps{Registry: reg, Auth: authConfig, Confirm: confirmStore, Audit: auditStore})
	handler := gateway.NewHTTPHandler(server, authConfig)
	ts := httptest.NewServer(handler)
	t.Cleanup(ts.Close)

	return &fixture{ts: ts, mutateCalls: mutateCalls}
}

type bearerRoundTripper struct{ token string }

func (b *bearerRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	req = req.Clone(req.Context())
	if b.token != "" {
		req.Header.Set("Authorization", "Bearer "+b.token)
	}
	return http.DefaultTransport.RoundTrip(req)
}

func (f *fixture) connect(ctx context.Context, token string) (*mcp.ClientSession, error) {
	client := mcp.NewClient(&mcp.Implementation{Name: "test-cli", Version: "0.0.1"}, nil)
	return client.Connect(ctx, &mcp.StreamableClientTransport{
		Endpoint:   f.ts.URL,
		HTTPClient: &http.Client{Transport: &bearerRoundTripper{token: token}},
	}, nil)
}

// --- tests ---------------------------------------------------------------

func TestInvalidToken_RejectedBeforeInteractiveLoop(t *testing.T) {
	f := newFixture(t)
	ctx := context.Background()

	_, err := f.connect(ctx, "not-a-real-token")
	if err == nil {
		t.Fatal("expected Connect to fail for an invalid token")
	}
	// Run is never reached in main() when Connect fails — nothing further
	// to assert here beyond the error itself.
}

func TestReadOnlyToolCall_PrintsResultWithNoConfirmationPrompt(t *testing.T) {
	f := newFixture(t)
	ctx := context.Background()
	session, err := f.connect(ctx, aliceToken)
	if err != nil {
		t.Fatalf("Connect: %v", err)
	}
	defer session.Close()

	in := strings.NewReader("echo\n{\"text\":\"hello\"}\n\n")
	var out bytes.Buffer
	if err := Run(ctx, session, in, &out); err != nil {
		t.Fatalf("Run: %v", err)
	}

	got := out.String()
	if !strings.Contains(got, `"echo":"hello"`) {
		t.Fatalf("expected the echo result in output, got:\n%s", got)
	}
	if strings.Contains(got, "confirm?") {
		t.Fatalf("read-only call must not print a confirmation prompt, got:\n%s", got)
	}
}

func TestConfirmFirstToolCall_ExecutesOnlyOnAffirmativeConfirmation(t *testing.T) {
	f := newFixture(t)
	ctx := context.Background()
	session, err := f.connect(ctx, aliceToken)
	if err != nil {
		t.Fatalf("Connect: %v", err)
	}
	defer session.Close()

	in := strings.NewReader("mutate\n{\"text\":\"hi\"}\ny\n\n")
	var out bytes.Buffer
	if err := Run(ctx, session, in, &out); err != nil {
		t.Fatalf("Run: %v", err)
	}

	got := out.String()
	if !strings.Contains(got, "pending confirmation: Mutate with text=hi") {
		t.Fatalf("expected the pending description in output, got:\n%s", got)
	}
	if !strings.Contains(got, `"mutated":true`) {
		t.Fatalf("expected the confirmed execution result in output, got:\n%s", got)
	}
	if got := atomic.LoadInt32(f.mutateCalls); got != 1 {
		t.Fatalf("expected exactly 1 execution of the mutating handler, got %d", got)
	}
}

func TestConfirmFirstToolCall_DecliningDoesNotExecute(t *testing.T) {
	f := newFixture(t)
	ctx := context.Background()
	session, err := f.connect(ctx, aliceToken)
	if err != nil {
		t.Fatalf("Connect: %v", err)
	}
	defer session.Close()

	in := strings.NewReader("mutate\n{\"text\":\"hi\"}\nn\n\n")
	var out bytes.Buffer
	if err := Run(ctx, session, in, &out); err != nil {
		t.Fatalf("Run: %v", err)
	}

	got := out.String()
	if !strings.Contains(got, "cancelled") {
		t.Fatalf("expected a cancellation message, got:\n%s", got)
	}
	if got := atomic.LoadInt32(f.mutateCalls); got != 0 {
		t.Fatalf("expected the mutating handler to never execute after declining, got %d calls", got)
	}
}
