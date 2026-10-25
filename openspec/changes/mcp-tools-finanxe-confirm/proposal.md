## Why

finanxe's real value beyond narration is taking action — redirecting debt
funding, tracking a new goal, adding a calendar reminder. Those are exactly
the actions that should never fire from a misheard voice command or a
misfired tool call without the human explicitly confirming first. This
change exposes finanxe's mutating endpoints through `gateway-core`'s
confirm-first flow, built and specced before any voice layer exists, so the
confirmation step is proven on a keyboard/CLI first.

## What Changes

- Extend the finanxe adapter (from `mcp-tools-finanxe-readonly`) with
  mutating tools: `finanxe_set_debt_funding`, `finanxe_create_goal`,
  `finanxe_add_calendar_event` (exact set finalized in design.md).
- Register each as `confirm-first` with `gateway-core`'s tool registry, so
  calling them returns a pending confirmation instead of executing
  immediately.
- Explicitly keep `/api/plaid/*` endpoints (token exchange, link token,
  sandbox connect, sync) unregistered — `never-by-voice` in spirit, and in
  Phase 1, simply not exposed as any tool at all.

## Capabilities

### New Capabilities
- `finanxe-mutating-tools`: confirm-first MCP tools for finanxe's debt funding, goal creation, and calendar mutation endpoints

### Modified Capabilities
(none — this adds tools, it does not change `finanxe-readonly-tools`' or `gateway-core`'s existing requirements)

## Impact

- New adapter code, depends on `gateway-core`'s confirmation flow and
  `mcp-tools-finanxe-readonly`'s existing finanxe adapter/base-URL config.
- No changes to the `finanxe` repository.
- First real exercise of the confirm-first flow end-to-end against a
  project that can actually change state.
