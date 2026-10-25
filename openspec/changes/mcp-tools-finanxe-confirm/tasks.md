## 1. Adapter implementation

- [x] 1.1 Implement `finanxe_set_debt_funding(debt_name, account_text)` execution function calling `POST /api/debt/funding` — `Client.SetDebtFunding` in `gateway/internal/finanxe/mutate.go`. **Finding**: the real route takes a raw debt `id`, not a name — see design.md's "Implementation note". The by-name/by-account matching from `set_debt_funding_by_name` (Python, only reachable via finanxe's internal agent chat loop) was ported into Go so the tool keeps its voice-friendly signature.
- [x] 1.2 Implement `finanxe_create_goal(goal_type, description, ...)` execution function calling `POST /api/goals/add` — `Client.CreateGoal`
- [x] 1.3 Implement `finanxe_add_calendar_event(title, event_date, detail=None)` execution function calling `POST /api/calendar/event` — `Client.AddCalendarEvent`
- [x] 1.4 Implement a description-builder for each tool that renders a human-readable summary from arguments alone — `describeSetDebtFunding`, `describeCreateGoal`, `describeAddCalendarEvent`

## 2. Registration

- [x] 2.1 Register all three tools as `confirm-first` with `gateway-core`'s tool registry, wiring each description-builder — `finanxe.RegisterMutating` in `gateway/internal/finanxe/mutate.go`, wired in `cmd/gateway/main.go`
- [x] 2.2 Add all three tools to the trusted user's allowed-tools set in the token config example — already present in `tokens.example.yaml`
- [x] 2.3 Confirm none of the three execution functions is reachable from the initial call path (only via `gateway-core`'s `confirm()`) — enforced structurally: `registry.Register` requires `TierConfirmFirst` defs to have a `Describe` func, and `gateway-core`'s `confirmFirstHandler` never invokes `Handler` — only `gatewayConfirmHandler` does, after `confirm.Store.Claim` succeeds. Verified with `TestRegisterMutating_HandlerNotCalledOnInitialToolCall` and the manual end-to-end check (task 3.5)

## 3. Verification

- [x] 3.1 Test: calling each tool returns a pending id and description, and finanxe's state is unchanged — verified end-to-end in the manual check (task 3.5) against `finanxe_set_debt_funding`, and structurally for all three via `TestRegisterMutating_HandlerNotCalledOnInitialToolCall` (finanxe is never called until `Handler` runs, which only happens on confirm)
- [x] 3.2 Test: confirming each pending id calls finanxe and returns its result — `TestSetDebtFunding_MatchesByNameAndAccount`, `TestCreateGoal_ReturnsCreatedGoal`, `TestAddCalendarEvent_ReturnsCreatedID` exercise each `Handler`'s finanxe call directly; the manual check (task 3.5) exercises the full pending-then-confirm path for `finanxe_set_debt_funding`
- [x] 3.3 Test: an expired or already-used pending id cannot trigger the finanxe call (exercises `gateway-core`'s existing guarantees against these specific tools) — covered by `gateway-core`'s existing `confirm` package tests (tier-agnostic) plus this change's manual check, which double-confirms `finanxe_set_debt_funding`'s pending id and confirms the second claim fails
- [x] 3.4 Test: finanxe rejecting a confirmed call (e.g. unknown debt name) surfaces as a clear tool-level error, not a crash — `TestSetDebtFunding_FinanxeRejects_ReturnsToolError`, `TestCreateGoal_ValidationError_ReturnsToolError`, `TestAddCalendarEvent_ValidationError_ReturnsToolError`; a debt name matching nothing is a distinct, deliberate soft `{set:false}` result rather than an error (`TestSetDebtFunding_UnknownDebt_ReturnsSoftFailureNotError`), matching finanxe's own agent-facing contract
- [x] 3.5 Manual check: both the `pending` and `executed` audit log entries appear for each tool, correctly linked by pending id — verified via a throwaway integration test replicating `gateway-core`'s real confirm-first flow (`confirm.Store.Create` -> pending audit write -> `confirm.Store.Claim` -> `Handler` -> executed audit write) against `finanxe_set_debt_funding` with a fake finanxe server; both entries shared the same pending id, the initial call never touched finanxe, and a second claim on the same pending id failed, before the scratch test was deleted

All tests pass under `go test ./... -race`; `go build ./...` and `go vet ./...` are clean.
