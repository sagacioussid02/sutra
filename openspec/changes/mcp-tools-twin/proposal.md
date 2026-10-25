## Why

twin is already a deployed, working conversational agent platform with its
own auth (Clerk) and a clean HTTP API. It's the lowest-risk project to wrap
first — proving the gateway's adapter pattern (call an existing API, expose
it as a tiered MCP tool) against a real, low-stakes backend before touching
finanxe's sensitive data.

## What Changes

- Add a twin adapter module that calls twin's existing HTTP API
  (`/chat`, `/twin/{id}`, `/public-personas`) — no changes to twin itself.
- Register `twin_chat` and `twin_list_public_personas` (naming finalized in
  design.md) as `read-only` tools with `gateway-core`'s tool registry.
- Configure the gateway with twin's base URL and whatever service
  credential is needed to call it on the user's behalf.

## Capabilities

### New Capabilities
- `twin-mcp-tools`: read-only MCP tools that let a gateway client chat with a twin persona and list available personas, backed by twin's existing deployed API

### Modified Capabilities
(none)

## Impact

- New adapter code only, depends on `gateway-core`'s tool registry and
  registration API.
- No changes to the `twin` repository.
- Requires a way for the gateway to authenticate to twin's API on behalf of
  the calling user (see design.md) — twin currently expects a Clerk JWT per
  end user, which the gateway does not have.
