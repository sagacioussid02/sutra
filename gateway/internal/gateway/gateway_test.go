package gateway

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/siddharthshankar/sutra/gateway/internal/audit"
	"github.com/siddharthshankar/sutra/gateway/internal/authcfg"
	"github.com/siddharthshankar/sutra/gateway/internal/confirm"
	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

// --- test fixture -----------------------------------------------------

const aliceToken = "alice-token"
const bobToken = "bob-token"

type fixture struct {
	ts           *httptest.Server
	audit        *audit.Store
	mutateCalls  *int32
}

func newFixture(t *testing.T) *fixture {
	t.Helper()

	mutateCalls := new(int32)

	reg := registry.New()
	reg.MustRegister(&registry.Definition{
		Name:        "echo",
		Tier:        registry.TierReadOnly,
		Description: "Echoes back the text argument.",
		Handler: func(ctx context.Context, userID string, args map[string]any) (any, error) {
			return map[string]any{"echo": args["text"], "user": userID}, nil
		},
	})
	reg.MustRegister(&registry.Definition{
		Name:        "mutate",
		Tier:        registry.TierConfirmFirst,
		Description: "A fake side-effecting action, gated by confirmation.",
		SecretArgs:  []string{"secret_field"},
		Describe: func(args map[string]any) string {
			return "Mutate with text=" + argString(args, "text")
		},
		Handler: func(ctx context.Context, userID string, args map[string]any) (any, error) {
			atomic.AddInt32(mutateCalls, 1)
			return map[string]any{"mutated": true}, nil
		},
	})
	reg.MustRegister(&registry.Definition{
		Name: "secret",
		Tier: registry.TierNeverByVoice,
	})

	tokensPath := writeTokens(t, `
users:
  - id: alice
    token: `+aliceToken+`
    allowed_tools:
      - echo
      - mutate
  - id: bob
    token: `+bobToken+`
    allowed_tools: []
`)
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

	server := NewMCPServer(Deps{Registry: reg, Auth: authConfig, Confirm: confirmStore, Audit: auditStore})
	handler := NewHTTPHandler(server, authConfig)
	ts := httptest.NewServer(handler)
	t.Cleanup(ts.Close)

	return &fixture{ts: ts, audit: auditStore, mutateCalls: mutateCalls}
}

func argString(args map[string]any, key string) string {
	s, _ := args[key].(string)
	return s
}

func writeTokens(t *testing.T, yaml string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "tokens.yaml")
	if err := os.WriteFile(path, []byte(yaml), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

type bearerRoundTripper struct {
	token string
}

func (b *bearerRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	req = req.Clone(req.Context())
	if b.token != "" {
		req.Header.Set("Authorization", "Bearer "+b.token)
	}
	return http.DefaultTransport.RoundTrip(req)
}

func (f *fixture) connect(t *testing.T, ctx context.Context, token string) *mcp.ClientSession {
	t.Helper()
	client := mcp.NewClient(&mcp.Implementation{Name: "test-client", Version: "0.0.1"}, nil)
	session, err := client.Connect(ctx, &mcp.StreamableClientTransport{
		Endpoint:   f.ts.URL,
		HTTPClient: &http.Client{Transport: &bearerRoundTripper{token: token}},
	}, nil)
	if err != nil {
		t.Fatalf("Connect: %v", err)
	}
	t.Cleanup(func() { session.Close() })
	return session
}

// --- tests --------------------------------------------------------------

func TestMissingTokenIsRejected(t *testing.T) {
	f := newFixture(t)
	resp, err := http.Post(f.ts.URL, "application/json", nil)
	if err != nil {
		t.Fatalf("POST: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 for missing token, got %d", resp.StatusCode)
	}
}

func TestInvalidTokenIsRejected(t *testing.T) {
	f := newFixture(t)
	req, _ := http.NewRequest(http.MethodPost, f.ts.URL, nil)
	req.Header.Set("Authorization", "Bearer not-a-real-token")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("request: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("expected 401 for invalid token, got %d", resp.StatusCode)
	}
}

func TestNeverByVoiceToolIsNotListedOrCallable(t *testing.T) {
	f := newFixture(t)
	ctx := context.Background()
	session := f.connect(t, ctx, aliceToken)

	tools, err := session.ListTools(ctx, nil)
	if err != nil {
		t.Fatalf("ListTools: %v", err)
	}
	for _, tool := range tools.Tools {
		if tool.Name == "secret" {
			t.Fatalf("never-by-voice tool %q must not appear in the tool list", tool.Name)
		}
	}

	_, err = session.CallTool(ctx, &mcp.CallToolParams{Name: "secret", Arguments: map[string]any{}})
	if err == nil {
		t.Fatal("expected calling a never-by-voice tool by name to fail, got nil error")
	}
}

func TestReadOnlyToolExecutesImmediately(t *testing.T) {
	f := newFixture(t)
	ctx := context.Background()
	session := f.connect(t, ctx, aliceToken)

	result, err := session.CallTool(ctx, &mcp.CallToolParams{
		Name:      "echo",
		Arguments: map[string]any{"text": "hello"},
	})
	if err != nil {
		t.Fatalf("CallTool echo: %v", err)
	}
	if result.IsError {
		t.Fatalf("expected success, got error result: %+v", result.Content)
	}

	entries, err := f.audit.Find(ctx, audit.Query{ToolName: "echo", Status: audit.StatusExecuted})
	if err != nil {
		t.Fatalf("audit.Find: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("expected 1 executed audit entry for echo, got %d", len(entries))
	}
}

func TestConfirmFirstToolIsHeldThenConfirmed(t *testing.T) {
	f := newFixture(t)
	ctx := context.Background()
	session := f.connect(t, ctx, aliceToken)

	result, err := session.CallTool(ctx, &mcp.CallToolParams{
		Name:      "mutate",
		Arguments: map[string]any{"text": "redirect funding", "secret_field": "sk-super-secret"},
	})
	if err != nil {
		t.Fatalf("CallTool mutate: %v", err)
	}
	if result.IsError {
		t.Fatalf("expected a pending confirmation, got error: %+v", result.Content)
	}
	if got := atomic.LoadInt32(f.mutateCalls); got != 0 {
		t.Fatalf("expected mutate handler NOT to run before confirmation, but it ran %d times", got)
	}

	var payload struct {
		PendingID   string `json:"pending_id"`
		Description string `json:"description"`
	}
	text := result.Content[0].(*mcp.TextContent).Text
	if err := json.Unmarshal([]byte(text), &payload); err != nil {
		t.Fatalf("unmarshal pending payload: %v", err)
	}
	if payload.PendingID == "" || payload.Description == "" {
		t.Fatalf("expected a pending id and description, got %+v", payload)
	}

	// Denied/pending call must not leak the secret argument into the audit log.
	pendingEntries, _ := f.audit.Find(ctx, audit.Query{ToolName: "mutate", Status: audit.StatusPending})
	if len(pendingEntries) != 1 || pendingEntries[0].Args["secret_field"] != "[REDACTED]" {
		t.Fatalf("expected secret_field redacted in pending audit entry, got %+v", pendingEntries)
	}

	// Confirm it.
	confirmResult, err := session.CallTool(ctx, &mcp.CallToolParams{
		Name:      authcfg.GatewayConfirmTool,
		Arguments: map[string]any{"pending_id": payload.PendingID},
	})
	if err != nil {
		t.Fatalf("CallTool gateway_confirm: %v", err)
	}
	if confirmResult.IsError {
		t.Fatalf("expected confirmation to succeed, got error: %+v", confirmResult.Content)
	}
	if got := atomic.LoadInt32(f.mutateCalls); got != 1 {
		t.Fatalf("expected mutate handler to run exactly once after confirmation, got %d", got)
	}

	executedEntries, _ := f.audit.Find(ctx, audit.Query{ToolName: "mutate", Status: audit.StatusExecuted})
	if len(executedEntries) != 1 || executedEntries[0].PendingID != payload.PendingID {
		t.Fatalf("expected an executed audit entry linked by pending id, got %+v", executedEntries)
	}

	// Re-confirming the same pending id must not execute it a second time.
	// Claim's rejection surfaces as a tool-level error result (like other
	// business errors), not a protocol-level Go error — see errorResult in
	// gatewayConfirmHandler.
	reconfirmResult, err := session.CallTool(ctx, &mcp.CallToolParams{
		Name:      authcfg.GatewayConfirmTool,
		Arguments: map[string]any{"pending_id": payload.PendingID},
	})
	if err != nil {
		t.Fatalf("CallTool gateway_confirm (second time): %v", err)
	}
	if !reconfirmResult.IsError {
		t.Fatal("expected an error result re-confirming an already-used pending id")
	}
	if got := atomic.LoadInt32(f.mutateCalls); got != 1 {
		t.Fatalf("expected mutate handler still to have run exactly once, got %d", got)
	}
}

func TestUnauthorizedToolCallIsDeniedAndLogged(t *testing.T) {
	f := newFixture(t)
	ctx := context.Background()
	session := f.connect(t, ctx, bobToken) // bob has an empty allowed_tools list

	_, err := session.CallTool(ctx, &mcp.CallToolParams{Name: "echo", Arguments: map[string]any{"text": "hi"}})
	if err == nil {
		t.Fatal("expected bob's call to echo to be denied, got nil error")
	}

	entries, findErr := f.audit.Find(ctx, audit.Query{UserID: "bob", ToolName: "echo", Status: audit.StatusDenied})
	if findErr != nil {
		t.Fatalf("audit.Find: %v", findErr)
	}
	if len(entries) != 1 {
		t.Fatalf("expected 1 denied audit entry for bob calling echo, got %d", len(entries))
	}
}
