## Context

finanxe's mutating routes relevant here: `POST /api/debt/funding` (backed by
`set_debt_funding_by_name` in `app.py`), `POST /api/goals/add` (backed by
`create_tracked_goal`), `POST /api/calendar/event` (backed by
`agent_add_calendar_event`). All are currently reachable by anyone who can
hit `127.0.0.1:8002`, with no confirmation step of their own — the gateway
is what adds one.

## Goals / Non-Goals

**Goals:**
- Route finanxe's three highest-value mutating actions through
  `gateway-core`'s confirm-first flow.
- Produce a human-readable description of each pending action good enough
  to read back to the user before they confirm (this is what will make the
  confirmation meaningful once voice exists).

**Non-Goals:**
- Debt add/update/delete, subscription changes, settings, memories,
  notifications — can follow as later changes once this pattern is proven.
- Any Plaid endpoint, at any tier — not addressed here; if finanxe ever
  needs the gateway to trigger a Plaid sync, that's a deliberate future
  change with its own review, not a byproduct of this one.

## Decisions

- **Tools exposed** (all `confirm-first`):
  - `finanxe_set_debt_funding(debt_name, account_text)` -> `POST /api/debt/funding`
  - `finanxe_create_goal(goal_type, description, ...)` -> `POST /api/goals/add`
  - `finanxe_add_calendar_event(title, event_date, detail=None)` -> `POST /api/calendar/event`
- **Confirmation description**: each tool's registration includes a
  description-builder function that turns the call's arguments into the
  human-readable string `gateway-core` returns with the pending id, e.g.
  `finanxe_set_debt_funding` renders as "Redirect funding for debt
  '<debt_name>' to account '<account_text>'." — built from the arguments,
  not from calling finanxe (finanxe is not invoked until confirmed).
- **No secret arguments** on these tools either (they operate on
  already-connected accounts/debts by name, not raw credentials) — declared
  explicitly as an empty set per `gateway-core`'s contract, same as the
  read-only tools.
- **Idempotency**: these finanxe endpoints are called for the first time
  only on confirmation; `gateway-core`'s "already-used pending id" rule
  (spec'd in `gateway-core`) prevents a double-confirm from double-firing
  the underlying finanxe call.

## Risks / Trade-offs

- The confirmation description is generated from arguments alone, before
  finanxe validates them — if finanxe would reject the call (e.g. unknown
  debt name), the user only finds out after confirming. Acceptable for
  Phase 1 (CLI client shows the error immediately after); worth revisiting
  before voice, where a failed confirmation needs a good spoken response.

## Implementation note (found during task 1.1)

`POST /api/debt/funding` (the actual REST route) takes a raw debt `id` and
`funding_account` string — it does **not** do name-based resolution.
`set_debt_funding_by_name` (the function this design's `debt_name` /
`account_text` signature was modeled on) only exists inside finanxe's
in-process agent chat tool-calling loop (`app.py`'s `do_POST` for `/chat`),
not as a standalone endpoint the gateway can call directly.

To keep `finanxe_set_debt_funding`'s voice-friendly by-name signature (the
whole point of routing this through the gateway rather than requiring a
raw debt id), the adapter ports `set_debt_funding_by_name`'s matching logic
into Go: fetch `GET /api/debts` (debts + `account_options`), match the debt
by exact/substring name and the account by digit-mask or token-overlap
scoring (same alias table: bofa/boa -> "bank of america", amex -> "american
express"), then call `POST /api/debt/funding` with the resolved debt id.
An unmatched debt name returns a soft `{set: false, note: "..."}` result
(matching the Python function's own contract), not a Go/tool-level error —
it isn't a finanxe/HTTP failure. See `gateway/internal/finanxe/mutate.go`.
