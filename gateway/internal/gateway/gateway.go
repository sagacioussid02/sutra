// Package gateway wires internal/registry, internal/authcfg,
// internal/confirm, and internal/audit into an actual MCP server and HTTP
// handler. It is the only package that knows about the MCP Go SDK.
package gateway

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	sdkauth "github.com/modelcontextprotocol/go-sdk/auth"
	"github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/siddharthshankar/sutra/gateway/internal/audit"
	"github.com/siddharthshankar/sutra/gateway/internal/authcfg"
	"github.com/siddharthshankar/sutra/gateway/internal/confirm"
	"github.com/siddharthshankar/sutra/gateway/internal/registry"
)

// Deps are the gateway's dependencies, built by main() and passed in
// rather than constructed here, so tests can substitute their own
// temp-dir-backed stores and a small registry of fake tools.
type Deps struct {
	Registry *registry.Registry
	Auth     *authcfg.Config
	Confirm  *confirm.Store
	Audit    *audit.Store
}

// confirmArgs is the gateway_confirm tool's input.
type confirmArgs struct {
	PendingID string `json:"pending_id" jsonschema:"the pending confirmation id returned by a confirm-first tool call"`
}

// NewMCPServer builds an *mcp.Server exposing every callable (non
// never-by-voice) tool in deps.Registry, plus the built-in gateway_confirm
// tool, with authorization and audit logging wired in.
func NewMCPServer(deps Deps) *mcp.Server {
	server := mcp.NewServer(&mcp.Implementation{
		Name:    "sutra-gateway",
		Version: "0.1.0",
	}, nil)

	server.AddReceivingMiddleware(authorizationMiddleware(deps))

	for _, def := range deps.Registry.Callable() {
		switch def.Tier {
		case registry.TierReadOnly:
			mcp.AddTool(server, &mcp.Tool{Name: def.Name, Description: def.Description}, readOnlyHandler(def, deps.Audit))
		case registry.TierConfirmFirst:
			mcp.AddTool(server, &mcp.Tool{Name: def.Name, Description: def.Description}, confirmFirstHandler(def, deps.Confirm, deps.Audit))
		default:
			// registry.Callable() already excludes TierNeverByVoice; this
			// default only guards against a future tier being added
			// without updating this switch.
			panic(fmt.Sprintf("gateway: unhandled tier %q for tool %q", def.Tier, def.Name))
		}
	}

	mcp.AddTool(server, &mcp.Tool{
		Name:        authcfg.GatewayConfirmTool,
		Description: "Confirm and execute a pending confirm-first tool call by its pending_id.",
	}, gatewayConfirmHandler(deps))

	return server
}

// NewHTTPHandler wraps server with the official SDK's streamable HTTP
// transport and bearer-token authentication middleware. It listens for
// localhost-only use in Phase 1; the caller decides the bind address.
func NewHTTPHandler(server *mcp.Server, authConfig *authcfg.Config) http.Handler {
	mcpHandler := mcp.NewStreamableHTTPHandler(func(req *http.Request) *mcp.Server {
		return server
	}, nil)

	requireAuth := sdkauth.RequireBearerToken(authConfig.Verifier(), &sdkauth.RequireBearerTokenOptions{
		// Phase 1 tokens are static and long-lived (manually issued and
		// revoked, per gateway-core's design.md) rather than short-lived
		// OAuth access tokens, so they carry no exp claim to check.
		AllowMissingExpiration: true,
	})

	return requireAuth(mcpHandler)
}

// authorizationMiddleware enforces gateway-authentication's requirement
// that every call to a registered tool be checked against the caller's
// allowed-tools set, and audits denials, before any tool-specific
// (read-only or confirm-first) handler runs.
func authorizationMiddleware(deps Deps) mcp.Middleware {
	return func(next mcp.MethodHandler) mcp.MethodHandler {
		return func(ctx context.Context, method string, req mcp.Request) (mcp.Result, error) {
			ctr, ok := req.(*mcp.CallToolRequest)
			if !ok {
				return next(ctx, method, req)
			}

			info := sdkauth.TokenInfoFromContext(ctx)
			if info == nil {
				// auth.RequireBearerToken already rejected unauthenticated
				// HTTP requests before the MCP layer runs; reaching here
				// without TokenInfo would be a wiring bug, not a normal
				// client error.
				return nil, fmt.Errorf("gateway: no authenticated user in context")
			}
			userID := info.UserID
			toolName := ctr.Params.Name

			if toolName == authcfg.GatewayConfirmTool {
				return next(ctx, method, req)
			}

			def, ok := deps.Registry.Lookup(toolName)
			if !ok {
				// Unknown tool name (including a never-by-voice tool,
				// which was never added to the server): let the SDK
				// return its own not-found error.
				return next(ctx, method, req)
			}

			if !deps.Auth.UserAllowed(userID, toolName) {
				_ = deps.Audit.Write(ctx, audit.Entry{
					UserID:        userID,
					ToolName:      toolName,
					Tier:          string(def.Tier),
					Status:        audit.StatusDenied,
					ResultSummary: "not authorized",
				})
				return nil, fmt.Errorf("gateway: user %q is not authorized to call tool %q", userID, toolName)
			}

			return next(ctx, method, req)
		}
	}
}

func userIDFromContext(ctx context.Context) string {
	if info := sdkauth.TokenInfoFromContext(ctx); info != nil {
		return info.UserID
	}
	return ""
}

func readOnlyHandler(def *registry.Definition, auditStore *audit.Store) mcp.ToolHandlerFor[map[string]any, any] {
	return func(ctx context.Context, _ *mcp.CallToolRequest, args map[string]any) (*mcp.CallToolResult, any, error) {
		userID := userIDFromContext(ctx)

		result, err := def.Handler(ctx, userID, args)

		status := audit.StatusExecuted
		summary := summarize(result)
		if err != nil {
			status = audit.StatusError
			summary = err.Error()
		}
		_ = auditStore.Write(ctx, audit.Entry{
			UserID:        userID,
			ToolName:      def.Name,
			Tier:          string(def.Tier),
			Args:          registry.Redact(args, def.SecretArgs),
			Status:        status,
			ResultSummary: summary,
		})

		if err != nil {
			return errorResult(err), nil, nil
		}
		return jsonResult(result), result, nil
	}
}

func confirmFirstHandler(def *registry.Definition, confirmStore *confirm.Store, auditStore *audit.Store) mcp.ToolHandlerFor[map[string]any, any] {
	return func(ctx context.Context, _ *mcp.CallToolRequest, args map[string]any) (*mcp.CallToolResult, any, error) {
		userID := userIDFromContext(ctx)
		description := def.Describe(args)

		pending, err := confirmStore.Create(ctx, userID, def.Name, args, description)
		if err != nil {
			_ = auditStore.Write(ctx, audit.Entry{
				UserID: userID, ToolName: def.Name, Tier: string(def.Tier),
				Args: registry.Redact(args, def.SecretArgs), Status: audit.StatusError, ResultSummary: err.Error(),
			})
			return errorResult(err), nil, nil
		}

		_ = auditStore.Write(ctx, audit.Entry{
			UserID:        userID,
			ToolName:      def.Name,
			Tier:          string(def.Tier),
			Args:          registry.Redact(args, def.SecretArgs),
			Status:        audit.StatusPending,
			PendingID:     pending.ID,
			ResultSummary: description,
		})

		payload := map[string]any{
			"pending_id":  pending.ID,
			"description": description,
			"expires_at":  pending.ExpiresAt.Format(time.RFC3339),
		}
		return jsonResult(payload), payload, nil
	}
}

func gatewayConfirmHandler(deps Deps) mcp.ToolHandlerFor[confirmArgs, any] {
	return func(ctx context.Context, _ *mcp.CallToolRequest, in confirmArgs) (*mcp.CallToolResult, any, error) {
		userID := userIDFromContext(ctx)

		rec, err := deps.Confirm.Claim(ctx, in.PendingID, userID)
		if err != nil {
			_ = deps.Audit.Write(ctx, audit.Entry{
				UserID: userID, ToolName: authcfg.GatewayConfirmTool, Tier: "system",
				Status: audit.StatusError, PendingID: in.PendingID, ResultSummary: err.Error(),
			})
			return errorResult(err), nil, nil
		}

		def, ok := deps.Registry.Lookup(rec.ToolName)
		if !ok {
			err := fmt.Errorf("gateway: tool %q is no longer registered", rec.ToolName)
			_ = deps.Audit.Write(ctx, audit.Entry{
				UserID: userID, ToolName: rec.ToolName, Status: audit.StatusError,
				PendingID: rec.ID, ResultSummary: err.Error(),
			})
			return errorResult(err), nil, nil
		}

		result, herr := def.Handler(ctx, userID, rec.Args)
		status := audit.StatusExecuted
		summary := summarize(result)
		if herr != nil {
			status = audit.StatusError
			summary = herr.Error()
		}
		_ = deps.Audit.Write(ctx, audit.Entry{
			UserID:        userID,
			ToolName:      rec.ToolName,
			Tier:          string(def.Tier),
			Args:          registry.Redact(rec.Args, def.SecretArgs),
			Status:        status,
			PendingID:     rec.ID,
			ResultSummary: summary,
		})

		if herr != nil {
			return errorResult(herr), nil, nil
		}
		return jsonResult(result), result, nil
	}
}

func jsonResult(v any) *mcp.CallToolResult {
	b, err := json.Marshal(v)
	if err != nil {
		return errorResult(err)
	}
	return &mcp.CallToolResult{Content: []mcp.Content{&mcp.TextContent{Text: string(b)}}}
}

func errorResult(err error) *mcp.CallToolResult {
	return &mcp.CallToolResult{
		IsError: true,
		Content: []mcp.Content{&mcp.TextContent{Text: err.Error()}},
	}
}

// summarize renders a short, log-friendly string for a handler result. It
// is only ever used for the audit log's result_summary column — the full
// result still goes to the MCP client via jsonResult.
func summarize(v any) string {
	b, err := json.Marshal(v)
	if err != nil {
		return fmt.Sprintf("<unmarshalable result: %v>", err)
	}
	const max = 500
	if len(b) > max {
		return string(b[:max]) + "...(truncated)"
	}
	return string(b)
}
