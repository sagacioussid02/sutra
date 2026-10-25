## Context

twin's backend (`~/workspace/AI/twin/backend/server.py`) exposes `/chat`,
`/twin/{twin_id}`, `/public-personas`, keyed by `session_id` for
conversation continuity, with `get_current_user_id` /
`get_current_user_email` as FastAPI dependencies that appear to support
both authenticated (Clerk JWT) and anonymous (session-id + IP tracked)
usage — twin already has an anonymous chat path (see `_should_notify_anon`,
`_client_ip`). This needs confirming against the actual dependency
signatures before implementation (task 1.1) rather than assumed.

## Goals / Non-Goals

**Goals:**
- Let a gateway client chat with a twin persona and list personas, without
  modifying twin.
- Keep each gateway user's twin conversation continuous across calls (map
  gateway user identity to a stable twin `session_id`).

**Non-Goals:**
- Persona *creation* (`/parse-linkedin`, persona intake flow) — read/chat
  only in this change.
- Solving twin-side multi-user Clerk auth from the gateway — if `/chat`
  turns out to strictly require a Clerk JWT with no anonymous path, this
  change's scope narrows to calling it as a single shared service identity
  (see Risks).

## Decisions

- **Adapter calls twin over HTTPS**, using twin's deployed API URL from
  config — not calling into twin's Python code directly, since twin runs on
  AWS Lambda, not locally.
- **Session mapping**: the adapter derives a stable `session_id` from the
  gateway user's identity (e.g. a deterministic hash of user id + twin id,
  matching twin's own `_derive_session_id` pattern) so repeated calls from
  the same gateway user continue the same twin conversation.
- **Tools exposed** (both `read-only`):
  - `twin_chat(twin_id, message)` -> calls `/chat`, returns twin's reply
  - `twin_list_public_personas()` -> calls `/public-personas`
- Persona creation and admin endpoints are intentionally not wrapped.

## Risks / Trade-offs

- If twin's `/chat` requires a genuine Clerk-issued JWT per user (no
  anonymous path), the gateway cannot mint one on a user's behalf without
  twin-side changes, which are out of scope for this change. In that case,
  fall back to calling `/chat` as a single shared "gateway service" twin
  identity — acceptable for Phase 1's "me + a few trusted users" scope, but
  loses per-user twin history separation. Task 1.1 verifies which case
  applies before the rest of the adapter is built.
