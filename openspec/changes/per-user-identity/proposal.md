## Why

Every caller of the gateway currently collapses into one finanxe
identity. `gateway/cmd/gateway/main.go` defines a single
`--finanxe-user-id` flag, defaulting to `demo_user`, described in its own
help text as "the finanxe user id every gateway caller maps to". The
owner's real financial data lives under that id, so the collapse is
invisible today — and the moment a second trusted person (a partner, a
family member) uses the assistant, it becomes a privacy failure: their
questions would read, and their confirm-first actions would write, the
owner's finances.

The rest of the system is already moving to per-person truth:
confirmations in the orchestrator are bound to the requesting speaker,
and memory is one database per user token. The gateway's identity
collapse is the remaining hole, and it is a foundation: `world-state`
assembles a snapshot for exactly one user, and `inbound-events`
attributes each event to one. Both need the mapping this change defines.

## What Changes

- **A caller→user mapping in gateway configuration.** Each bearer token
  maps to a user id. The gateway resolves the caller to that user id on
  every request and passes it to adapters instead of any global default.
- **The finanxe adapter takes the mapped user id.** The single
  `--finanxe-user-id` flag stops being the identity for all callers. It
  survives only as an explicit fallback for one legacy token if the
  operator configures it that way, and every fallback use is audit-logged
  as a fallback.
- **The twin adapter is checked for the same collapse** and given the
  same treatment if it maps callers to a shared upstream identity.
- **Audit records the effective user.** Every audit entry gains the
  resolved user id (it already records caller identity), so "whose data
  did this call touch?" is always answerable.
- **No silent cross-user reads.** A request whose token has no mapping
  fails closed: read tools return an identity error, and nothing falls
  back to another user's id. There is no code path where an unmapped or
  mismatched caller receives the owner's data.
- **Migration without moving data.** The owner's existing finanxe data
  stays under `demo_user`; the migration is a mapping entry that points
  the owner's token at `demo_user` explicitly. Other users get their own
  finanxe ids as finanxe supports them; finanxe itself is not modified,
  per the project's conventions.
- Out of scope, deliberately: a new authentication system (bearer tokens
  stay, per the project constraints), multi-user support inside finanxe
  or twin, per-user finanxe databases, and user management UI — the
  mapping is a configuration file the operator edits.

## Capabilities

### New Capabilities
- `per-user-identity`: every gateway caller resolves to exactly one user id from configuration, adapters receive that id, unmapped callers fail closed, and the effective user is audited on every call

### Modified Capabilities
(none — `gateway-core` already requires caller identity in the audit; this change supplies the resolution it records)

## Impact

- Gateway: identity resolution in the request path, a mapping file in
  configuration, adapter call sites updated (finanxe first, twin if
  needed), audit entry gains the effective user id.
- Orchestrator: no changes required; its per-token memory databases and
  speaker-bound confirmations compose with the gateway mapping (the same
  token should map to the same person in both places — called out in
  design as an operator responsibility with a startup warning).
- Depends on `gateway-core` (auth and audit) and `mcp-tools-finanxe-readonly`
  / `mcp-tools-finanxe-confirm` (the adapter call sites). Foundations for
  `world-state` and `inbound-events`.
- Configuration gains a sensitive file (token→user mapping), handled like
  other secrets: never committed, documented by an example with
  placeholders only, and every variable documented in `.env.example`.
