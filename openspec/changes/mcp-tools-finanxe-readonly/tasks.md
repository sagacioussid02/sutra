## 1. Adapter implementation

- [x] 1.1 Add finanxe base URL (`http://127.0.0.1:8002`) to gateway config — `-finanxe-base-url` flag in `gateway/cmd/gateway/main.go`
- [x] 1.2 Implement gateway-user-id -> finanxe-user-id mapping (single real user for now, per design.md) — `-finanxe-user-id` flag, defaulting to `finanxe.DefaultUserID` ("default_user", matching finanxe's own fallback); `Client` ignores the gateway-authenticated user id entirely and always uses the configured finanxe user id
- [x] 1.3 Implement `finanxe_get_snapshot()` calling `GET /api/snapshot` — `Client.GetSnapshot`
- [x] 1.4 Implement `finanxe_list_debts()` calling `GET /api/debts` — `Client.ListDebts`
- [x] 1.5 Implement `finanxe_get_calendar()` calling `GET /api/calendar` — `Client.GetCalendar`
- [x] 1.6 Implement `finanxe_list_goals()` calling `GET /api/goals` — `Client.ListGoals`
- [x] 1.7 Handle finanxe unreachable / non-200 responses as tool-level errors, not gateway crashes — `Client.get` wraps connection failures and non-200 status as errors; never panics

## 2. Registration

- [x] 2.1 Register all four tools as `read-only` with `gateway-core`'s tool registry, each with an empty secret-args set — `finanxe.Register` in `gateway/internal/finanxe/finanxe.go`, wired in `cmd/gateway/main.go`
- [x] 2.2 Add all four tools to the trusted user's allowed-tools set in the token config example — already present in `tokens.example.yaml`
- [x] 2.3 Confirm no `/api/plaid/*` or mutating finanxe route is referenced anywhere in the adapter — verified by grep (task 3.4)

## 3. Verification

- [x] 3.1 Test: each tool against a running local finanxe instance returns finanxe's actual response shape — `TestGetSnapshot_ReturnsData`, `TestListDebts_ReturnsData`, `TestGetCalendar_ReturnsData`, `TestListGoals_ReturnsData` (against an `httptest.Server` shaped like finanxe's real responses, since no local finanxe instance was running to test against directly)
- [x] 3.2 Test: each tool against finanxe not running returns a tool-level error — `TestFinanxeUnreachable_ReturnsToolError`, `TestNonOKStatus_ReturnsToolError`
- [x] 3.3 Manual check: all four tool calls appear correctly in the gateway's audit log — verified via a throwaway integration test wiring `finanxe.Register` + `audit.Store` together against a fake finanxe server; all four tools wrote correct entries (tool name, tier, args, result) before the scratch test was deleted
- [x] 3.4 Manual check: grep the adapter module for `/api/plaid` and any write-route path — confirm zero matches — `grep` found only the explanatory doc comment in `finanxe.go` stating the package never calls those routes; no actual reference

All tests pass under `go test ./... -race`; `go build ./...` and `go vet ./...` are clean.
