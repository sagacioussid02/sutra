## Context

finanxe's backend (`~/workspace/AI/finanxe/poc/backend/app.py`) is a stdlib
`http.server` app bound to `127.0.0.1:8002` with routes including
`/api/snapshot`, `/api/debts`, `/api/calendar`, `/api/goals`,
`/api/subscriptions`, `/api/digest`, `/api/profile`, `/api/alerts`,
`/api/transactions`, `/api/budget-plan` (GET, all currently
unauthenticated — reachability is today's only control, which is exactly
why the gateway must be the sole caller). Mutating and Plaid-token routes
(`/api/debt/*` writes, `/api/goals/add|update|delete`,
`/api/calendar/event*`, `/api/plaid/*`) exist on the same server but are
out of scope for this change.

## Goals / Non-Goals

**Goals:**
- Expose finanxe's core read surface (snapshot, debts, calendar, goals)
  through the gateway as `read-only` tools.
- Keep finanxe itself unmodified and localhost-only.

**Non-Goals:**
- Any mutating finanxe endpoint — that's `mcp-tools-finanxe-confirm`.
- Any Plaid endpoint — never exposed as a gateway tool in Phase 1.
- Subscriptions, digest, alerts, transactions-by-category — can be added as
  a follow-up change once the core four tools are proven; not required for
  the Phase 1 CLI milestone.

## Decisions

- **Adapter calls finanxe over HTTP** to `127.0.0.1:8002`, the same pattern
  as the twin adapter, rather than importing finanxe's Python modules
  in-process — keeps the gateway decoupled from finanxe's process
  lifecycle and avoids sharing finanxe's SQLite connection across processes.
- **User scoping**: finanxe's endpoints take a `user_id` (see
  `account_options(user_id)`, `goals_with_progress(user_id)` etc. in
  `app.py`). The adapter passes the gateway-authenticated user's id through
  as finanxe's `user_id` — this requires the gateway user id and finanxe's
  existing user id scheme to align; if finanxe currently only has one real
  user (`DEMO_USER_ID`-style), the adapter maps every gateway-authorized
  finanxe caller to that one finanxe user id for now (single real user,
  same as finanxe's current reality) rather than inventing multi-user
  support finanxe doesn't have.
- **Tools exposed** (all `read-only`):
  - `finanxe_get_snapshot()` -> `GET /api/snapshot`
  - `finanxe_list_debts()` -> `GET /api/debts`
  - `finanxe_get_calendar()` -> `GET /api/calendar`
  - `finanxe_list_goals()` -> `GET /api/goals`
- **No secret arguments** on these tools (they take no financial-credential
  input), so audit log redaction is a no-op here — still declared
  explicitly (empty set) per `gateway-core`'s registration contract.

## Risks / Trade-offs

- finanxe has no auth of its own today; anything on the same machine that
  can reach `127.0.0.1:8002` can already call these endpoints directly,
  bypassing the gateway. This change does not fix that (out of scope — it's
  a finanxe-repo change, not a gateway one) but the architecture note in
  the main README should keep flagging it as a known gap until addressed.
- Mapping all gateway users to a single finanxe user id is a deliberate
  short-term simplification; revisit if finanxe grows real multi-user
  support.
