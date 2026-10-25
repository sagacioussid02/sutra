// Command gateway runs the Sutra MCP gateway: a single local process that
// authenticates trusted users, dispatches tiered tool calls (read-only,
// confirm-first, never-by-voice), and audits every attempt.
//
// This binary, by itself, registers no project-specific tools — that is
// deliberate (see openspec/changes/gateway-core/proposal.md). Tools for
// twin and finanxe are added by adapter packages in later changes, which
// will call registry.Register from their own init/wiring code before
// gateway.NewMCPServer runs.
package main

import (
	"context"
	"flag"
	"log"
	"net/http"
	"os"

	"github.com/siddharthshankar/sutra/gateway/internal/audit"
	"github.com/siddharthshankar/sutra/gateway/internal/authcfg"
	"github.com/siddharthshankar/sutra/gateway/internal/confirm"
	"github.com/siddharthshankar/sutra/gateway/internal/discovery"
	"github.com/siddharthshankar/sutra/gateway/internal/discoverysrc"
	"github.com/siddharthshankar/sutra/gateway/internal/finanxe"
	"github.com/siddharthshankar/sutra/gateway/internal/gateway"
	"github.com/siddharthshankar/sutra/gateway/internal/genericadapter"
	"github.com/siddharthshankar/sutra/gateway/internal/manifest"
	"github.com/siddharthshankar/sutra/gateway/internal/registry"
	"github.com/siddharthshankar/sutra/gateway/internal/twin"
)

func main() {
	addr := flag.String("addr", "127.0.0.1:8765", "address to listen on (localhost-only in Phase 1)")
	tokensPath := flag.String("tokens", "tokens.yaml", "path to the gitignored token config (see tokens.example.yaml)")
	auditDBPath := flag.String("audit-db", "sutra-audit.db", "path to the audit log SQLite database")
	confirmDBPath := flag.String("confirm-db", "sutra-confirm.db", "path to the pending-confirmations SQLite database")
	confirmTTL := flag.Duration("confirm-ttl", confirm.DefaultTTL, "how long a confirm-first pending call remains confirmable")
	// Verified reachable 2026-09-14: u6bux35z34 (twin/frontend/.env.production's
	// value at the time mcp-tools-twin was implemented) has since gone NXDOMAIN
	// — 2u95puvzsd (from .env.local, despite the name) is twin's actual live
	// API Gateway endpoint. Re-verify against twin's current deployment if this
	// ever stops resolving.
	twinBaseURL := flag.String("twin-base-url", "https://2u95puvzsd.execute-api.us-east-2.amazonaws.com", "twin's deployed API base URL")
	twinSessionSecret := flag.String("twin-session-secret", os.Getenv("TWIN_SESSION_SECRET"), "optional secret used to HMAC-derive twin session ids (defaults to $TWIN_SESSION_SECRET)")
	finanxeBaseURL := flag.String("finanxe-base-url", "http://127.0.0.1:8002", "finanxe's local API base URL")
	// Verified 2026-09-14: the user's real, actually-seeded finanxe data lives
	// under "demo_user" (finanxe's own DEMO_USER_ID), not "default_user" (the
	// bare query-param fallback finanxe.DefaultUserID documents). Defaulting
	// here to "demo_user" means the gateway works against real data out of the
	// box; override with -finanxe-user-id if finanxe ever gets real multi-user
	// support and this needs to vary per gateway user.
	finanxeUserID := flag.String("finanxe-user-id", "demo_user", "the finanxe user id every gateway caller maps to (finanxe has no real multi-user support today)")
	discoveryDBPath := flag.String("discovery-db", "sutra-discovery.db", "path to the discovery approval SQLite database")
	discoverySourcesPath := flag.String("discovery-sources", "discovery-sources.yaml", "path to the discovery sources config (optional — see discovery-sources.example.yaml)")
	flag.Parse()

	authConfig, err := authcfg.Load(*tokensPath)
	if err != nil {
		log.Fatalf("gateway: loading token config: %v", err)
	}

	auditStore, err := audit.Open(*auditDBPath)
	if err != nil {
		log.Fatalf("gateway: opening audit log: %v", err)
	}
	defer auditStore.Close()

	confirmStore, err := confirm.Open(*confirmDBPath, *confirmTTL)
	if err != nil {
		log.Fatalf("gateway: opening confirmation store: %v", err)
	}
	defer confirmStore.Close()

	reg := registry.New()
	twinClient := twin.NewClient(twin.Config{
		BaseURL:       *twinBaseURL,
		SessionSecret: *twinSessionSecret,
	})
	if err := twin.Register(reg, twinClient); err != nil {
		log.Fatalf("gateway: registering twin tools: %v", err)
	}
	finanxeClient := finanxe.NewClient(finanxe.Config{
		BaseURL: *finanxeBaseURL,
		UserID:  *finanxeUserID,
	})
	if err := finanxe.Register(reg, finanxeClient); err != nil {
		log.Fatalf("gateway: registering finanxe tools: %v", err)
	}
	if err := finanxe.RegisterMutating(reg, finanxeClient); err != nil {
		log.Fatalf("gateway: registering finanxe mutating tools: %v", err)
	}

	discoveryStore, err := discovery.Open(*discoveryDBPath)
	if err != nil {
		log.Fatalf("gateway: opening discovery approval store: %v", err)
	}
	defer discoveryStore.Close()

	discoverySources, err := discoverysrc.Load(*discoverySourcesPath)
	if err != nil {
		log.Fatalf("gateway: loading %s: %v", *discoverySourcesPath, err)
	}
	registerDiscoveredTools(reg, discoveryStore, discoverySources.Sources)

	server := gateway.NewMCPServer(gateway.Deps{
		Registry: reg,
		Auth:     authConfig,
		Confirm:  confirmStore,
		Audit:    auditStore,
	})
	handler := gateway.NewHTTPHandler(server, authConfig)

	log.SetOutput(os.Stderr)
	log.Printf("sutra gateway listening on http://%s (tools registered: %d)", *addr, len(reg.Callable()))
	if err := http.ListenAndServe(*addr, handler); err != nil {
		log.Fatalf("gateway: %v", err)
	}
}

// registerDiscoveredTools registers every approved, generically callable
// tool from each configured discovery source. A source whose manifest
// can't be fetched right now (the backend is down, unreachable, etc.) is
// logged and skipped for this run — a down backend must never prevent the
// gateway itself from starting.
func registerDiscoveredTools(reg *registry.Registry, store *discovery.Store, sources []discoverysrc.Source) {
	if len(sources) == 0 {
		return
	}

	ctx := context.Background()
	approvals, err := store.Approved(ctx)
	if err != nil {
		log.Fatalf("gateway: reading approved discovered tools: %v", err)
	}

	for _, src := range sources {
		m, err := manifest.Fetch(ctx, http.DefaultClient, src.ManifestURL)
		if err != nil {
			log.Printf("gateway: discovery: %s: could not fetch manifest, skipping this run: %v", src.Name, err)
			continue
		}

		client := genericadapter.NewClient(genericadapter.Config{BaseURL: src.BaseURL})
		registered, skipped := genericadapter.RegisterApproved(reg, src.Name, client, m.Tools, approvals)
		log.Printf("gateway: discovery: %s: registered %d discovered tool(s) (%d skipped)", src.Name, registered, skipped)
	}
}
