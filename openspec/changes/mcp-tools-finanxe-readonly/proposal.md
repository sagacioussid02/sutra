## Why

finanxe holds the user's real financial picture and is the main reason the
gateway needs auth, tiering, and an audit log before anything else. The
read-only surface (snapshot, debts, calendar, goals) is where finanxe
becomes useful through the gateway with the least risk — no side effects,
no money-moving, no Plaid token handling. This change proves the adapter
pattern against finanxe specifically before the mutating tools
(`mcp-tools-finanxe-confirm`) are added on top of `gateway-core`'s
confirmation flow.

## What Changes

- Add a finanxe adapter module that calls finanxe's existing local HTTP API
  (`127.0.0.1:8002`) — no changes to finanxe itself.
- Register read-only finanxe endpoints as `read-only` MCP tools:
  `finanxe_get_snapshot`, `finanxe_list_debts`, `finanxe_get_calendar`,
  `finanxe_list_goals` (exact set finalized in design.md).
- Explicitly do **not** register any endpoint that touches Plaid tokens
  (`/api/plaid/*`) or mutates state — those are out of scope here and, for
  the Plaid endpoints specifically, out of scope for the gateway entirely
  per the architecture (`never-by-voice` / not exposed).

## Capabilities

### New Capabilities
- `finanxe-readonly-tools`: read-only MCP tools exposing finanxe's financial snapshot, debts, calendar, and goals data

### Modified Capabilities
(none)

## Impact

- New adapter code only, depends on `gateway-core`'s tool registry.
- No changes to the `finanxe` repository or its running process.
- Requires finanxe's local server to be running and reachable at
  `127.0.0.1:8002` when the gateway starts — the gateway does not manage
  finanxe's lifecycle in this change.
