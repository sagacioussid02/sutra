// Command sutra-cli is a text client for the Sutra gateway: the Phase 1
// milestone that proves auth, tiered dispatch, the confirm-first flow, and
// audit logging work end to end before any voice layer exists. See
// openspec/changes/gateway-cli-client for the walkthrough this exercises.
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"

	"github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/siddharthshankar/sutra/gateway/internal/cliapp"
)

func main() {
	addr := flag.String("addr", "http://127.0.0.1:8765", "the gateway's address")
	token := flag.String("token", os.Getenv("SUTRA_TOKEN"), "bearer token for this session (defaults to $SUTRA_TOKEN)")
	flag.Parse()

	if *token == "" {
		log.Fatal("sutra-cli: a bearer token is required (-token or $SUTRA_TOKEN)")
	}

	ctx := context.Background()

	client := mcp.NewClient(&mcp.Implementation{Name: "sutra-cli", Version: "0.1.0"}, nil)
	transport := &mcp.StreamableClientTransport{
		Endpoint:   *addr,
		HTTPClient: &http.Client{Transport: bearerTokenTransport{token: *token}},
	}

	session, err := client.Connect(ctx, transport, nil)
	if err != nil {
		fmt.Fprintf(os.Stderr, "sutra-cli: authentication or connection failed: %v\n", err)
		os.Exit(1)
	}
	defer session.Close()

	if err := cliapp.Run(ctx, session, os.Stdin, os.Stdout); err != nil {
		log.Fatalf("sutra-cli: %v", err)
	}
}

// bearerTokenTransport adds the configured bearer token to every request,
// so the gateway's auth.RequireBearerToken middleware sees it on the
// initial connect as well as every subsequent tool call.
type bearerTokenTransport struct {
	token string
	base  http.RoundTripper
}

func (t bearerTokenTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	base := t.base
	if base == nil {
		base = http.DefaultTransport
	}
	req = req.Clone(req.Context())
	req.Header.Set("Authorization", "Bearer "+t.token)
	return base.RoundTrip(req)
}
