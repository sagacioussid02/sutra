## Context

Sutra will eventually front multiple existing agent projects and a voice
orchestrator. Phase 1 targets two projects (twin, finanxe) reachable from a
CLI client (see `gateway-cli-client`). This design covers only the shared
gateway infrastructure those adapters and clients will build on.

Language/runtime: Go. The gateway is a thin network proxy and policy layer
(auth check, tier dispatch, confirm/expire, audit write), not domain logic —
both `mcp-tools-twin` and `mcp-tools-finanxe-readonly`/`-confirm` call their
backends over HTTP rather than in-process, so the gateway has no need to
share a runtime with twin or finanxe. Go gives a single static binary
(cheap to deploy, matches the "prefer cheap/simple hosting" constraint, and
cross-compiles for the Raspberry Pi if ever needed there), a compile-time
enum for the tier system, and goroutines/`context` that fit a
confirmation-TTL and audit-writing proxy well. Uses the official
`github.com/modelcontextprotocol/go-sdk` and a pure-Go SQLite driver
(`modernc.org/sqlite`, no cgo — keeps cross-compilation simple).

## Goals / Non-Goals

**Goals:**
- One process, run locally, that every tool call passes through.
- Tool tiering enforced centrally — an adapter cannot bypass confirm-first
  by calling the underlying function directly through the gateway.
- Auth simple enough to run with a handful of trusted users, not a full
  identity system.
- Audit log that is queryable after the fact (who called what, when, with
  what result) without needing to parse free-text logs.

**Non-Goals:**
- Multi-tenancy, tenant isolation, billing — out of scope (audience is the
  user plus a few trusted people).
- Network exposure beyond localhost — no public port in this change.
- Voice/LiveKit integration — that's Phase 2.
- Any twin- or finanxe-specific tool logic — that's the two `mcp-tools-*`
  changes.

## Decisions

- **MCP server implementation**: `github.com/modelcontextprotocol/go-sdk`'s
  streamable HTTP transport (`mcp.NewStreamableHTTPHandler`), localhost-only
  in Phase 1, so any MCP-compatible client (including a future LiveKit
  agent) can connect without a custom protocol.
- **Tool registry**: an in-process Go registry populated at startup by
  adapter packages (`mcp-tools-twin`, `mcp-tools-finanxe-*` each register
  their tools with a tier via a shared `Registration` type). The registry is
  the single place tier is declared — adapters do not make that decision
  per-call.
- **One shared MCP server, authorization enforced by MCP-level middleware**:
  the SDK's `auth.RequireBearerToken` HTTP middleware resolves the bearer
  token to a user and stashes it in request context before the streamable
  HTTP handler runs; a single `mcp.Server` (shared across all users) then
  uses `AddReceivingMiddleware` to check, on every `CallTool`, whether the
  authenticated user's allowed-tools set includes the requested tool —
  denying and audit-logging before the tool's own handler ever runs. All
  non-`never-by-voice` tools are listed to every authenticated user (tool
  *listing* is not filtered per user); only *calling* an unlisted-for-you
  tool is denied. This was chosen over building a distinct `*mcp.Server`
  per user specifically so that a denial is always attributable and
  auditable — a tool simply absent from a per-user server's tool list would
  make "denied call" events unreachable to log.
- **Auth**: a static config file (not committed — see `.gitignore`) mapping
  bearer token -> user id -> allowed tool names. Loaded at startup. No token
  issuance/rotation UI in this change; tokens are generated and distributed
  manually.
- **Confirmation flow**: calling a `confirm-first` tool returns a pending
  confirmation id and a human-readable description of the action instead of
  executing it. A separate `confirm(pending_id)` gateway call executes the
  original tool call. Pending confirmations expire after a short TTL (e.g.
  5 minutes) to avoid stale actions firing much later.
- **Audit log storage**: SQLite file, one `audit_log` table. Columns: id,
  timestamp, user_id, tool_name, tier, args_redacted (JSON), status
  (`denied`/`pending`/`confirmed`/`executed`/`error`), result_summary.
  Argument redaction is tool-declared (each tool registration lists which
  argument names are secrets and must be masked before logging).
- **`never-by-voice` tier**: tools of this tier are simply never registered
  in the callable tool list in Phase 1 — the tier exists in the type system
  so it's a deliberate choice to add such a tool later (Phase 2+, once
  speaker-verification or similar exists), not an oversight.

- **Pre-authentication denials are not tool-attributed in the audit log.**
  `auth.RequireBearerToken` rejects a missing/invalid bearer token at the
  raw HTTP layer, before the JSON-RPC body (which names the tool) is ever
  parsed — so there is no tool name available to log at that point. Only
  authenticated-but-not-allowed-for-this-tool denials, which happen one
  layer up inside the MCP method middleware after the tool name is known,
  produce an audited `denied` entry with a tool name attached. This is a
  deliberate scope boundary, not an oversight: a missing/invalid token
  never gets far enough to reach any tool-specific state.

## Risks / Trade-offs

- A static token file is simple but manual — acceptable at "a few trusted
  users" scale; revisit if the user count or attack surface grows before
  Phase 3's platform work.
- SQLite for the audit log is single-writer; fine for one local gateway
  process, would need revisiting if the gateway is ever horizontally scaled.
- Confirmation TTL is a guess (5 min) — may need tuning once real usage
  (especially voice, where the round trip is conversational) is observed.
