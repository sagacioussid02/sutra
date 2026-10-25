## Why

The four preceding changes build the gateway and its tools, but none of
them produce something the user can actually sit down and use. This change
is the Phase 1 milestone: a text client that proves the whole path — auth,
tiered dispatch, confirmation, audit — works end to end before any voice
work starts. If this doesn't feel right to use from a keyboard, it won't
feel right from voice either.

## What Changes

- Add a CLI client (separate process/script from the gateway) that
  authenticates with a bearer token, lists available tools, calls a tool,
  and handles the confirm-first flow interactively (show the pending
  description, ask the user to confirm or cancel).
- Provide a scripted or documented walkthrough: ask twin a question, ask
  finanxe for a snapshot, attempt a finanxe mutation and see it held for
  confirmation, confirm it, and see it audited.

## Capabilities

### New Capabilities
- `gateway-cli-client`: an interactive text client for exercising the gateway's full tool-call and confirmation flow

### Modified Capabilities
(none)

## Impact

- New client code only, depends on all four prior changes being complete
  (`gateway-core`, `mcp-tools-twin`, `mcp-tools-finanxe-readonly`,
  `mcp-tools-finanxe-confirm`).
- No changes to twin, finanxe, or the gateway's own internals — this is a
  consumer of the MCP interface those changes expose.
