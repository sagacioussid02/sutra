## Why

Every downstream capability Sutra will ever expose — twin, finanxe, voice,
eventually hardware — has to pass through one chokepoint that knows who is
calling, what tool they're calling, whether that tool needs confirmation
before it runs, and that records what happened. Building that chokepoint
first, before any project-specific tool exists, means finanxe's sensitive
financial data and side-effecting actions are never reachable without auth,
tiering, and an audit trail — not even for a day during development.

## What Changes

- Stand up the Sutra gateway as a single local MCP server process.
- Add a tool registry where every registered tool declares a tier:
  `read-only`, `confirm-first`, or `never-by-voice`.
- Add per-user bearer-token authentication, with each token mapped to the
  set of tools/projects that user may call.
- Add a confirm-first flow: a `confirm-first` tool call is held pending;
  the caller must submit an explicit confirmation (matching a pending call
  id) before it executes.
- Add an audit log: every tool invocation attempt (allowed, denied, pending,
  confirmed, executed) is recorded with caller identity, tool name, redacted
  arguments, result, and timestamp.
- No project-specific tools are registered in this change — it is
  infrastructure only, proven with a placeholder/example tool in tests.

## Capabilities

### New Capabilities
- `mcp-gateway-server`: the gateway process, its tool registry, and tiering rules
- `gateway-authentication`: per-user bearer tokens and tool/project access mapping
- `gateway-audit-log`: durable audit log of every tool call attempt
- `tool-confirmation-flow`: hold-and-confirm mechanism for `confirm-first` tools

### Modified Capabilities
(none — this is the first change)

## Impact

- New code only, in a new `gateway/` directory in this repo (or similar —
  finalized in design.md). No changes to twin or finanxe.
- Introduces local storage for the audit log (SQLite, per project.md's
  preference for cheap/simple infra) and for pending confirmations.
- Establishes the token -> allowed-tools mapping format that
  `mcp-tools-twin` and `mcp-tools-finanxe-*` will register into.
