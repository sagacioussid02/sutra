## 1. CLI implementation

- [x] 1.1 Set up CLI project (script or small package) with MCP client library, matching the gateway's chosen transport — `gateway/cmd/sutra-cli/main.go`, using the same `mcp.StreamableClientTransport` the gateway serves
- [x] 1.2 Implement token-based connection and startup tool-list fetch — bearer token injected via `bearerTokenTransport` RoundTripper (`main.go`); tool list printed at the start of `cliapp.Run`
- [x] 1.3 Implement the interactive loop: choose tool, supply arguments, dispatch — `cliapp.Run` in `gateway/internal/cliapp/cliapp.go` (tool name prompt, JSON-argument prompt, `CallTool` dispatch)
- [x] 1.4 Implement the confirm-first branch: print description, require explicit affirmative input, call `confirm()` or cancel — `callAndHandle` detects a `pending_id` in the result, prints description/expiry, requires `y`/`yes`, calls `gateway_confirm`
- [x] 1.5 Print clear, distinct output for read-only results vs. pending-confirmation vs. confirmed-execution results — `result: ...` / `pending confirmation: ...` + `confirm? [y/N]>` / `confirmed — result: ...` / `cancelled — nothing was executed`

## 2. Walkthrough

- [x] 2.1 Write a short README/usage doc for the CLI covering setup (token, gateway address) — `gateway/cmd/sutra-cli/README.md`
- [x] 2.2 Document the three-step walkthrough: twin chat, finanxe snapshot, finanxe mutation with confirmation — same README, "Walkthrough" section
- [x] 2.3 Run the walkthrough manually against a real local gateway + finanxe + twin, fix any friction found — ran the real built `sutra-gateway` and `sutra-cli` binaries end-to-end. This sandbox has no network access (DNS resolution is blocked) and no local finanxe running, so twin and finanxe were backed by small local HTTP stand-ins (`/public-personas`, `/chat`, `/api/snapshot`, `/api/debts`, `/api/debt/funding`) rather than the real deployed twin / a real finanxe process — everything else (the gateway process, the CLI binary, the MCP transport, the confirm flow, the audit log) was real. All three steps worked on the first run with no friction found; output and the resulting audit log are captured in this task's history.

## 3. Verification

- [x] 3.1 Test: invalid token is rejected before the interactive loop starts — `TestInvalidToken_RejectedBeforeInteractiveLoop`
- [x] 3.2 Test: a read-only tool call prints a result with no confirmation prompt — `TestReadOnlyToolCall_PrintsResultWithNoConfirmationPrompt`
- [x] 3.3 Test: a confirm-first call prints the description and only executes on explicit affirmative input — `TestConfirmFirstToolCall_ExecutesOnlyOnAffirmativeConfirmation`
- [x] 3.4 Test: declining a confirm-first call does not mutate the underlying project's state — `TestConfirmFirstToolCall_DecliningDoesNotExecute` (asserts the mutating handler's call count stays 0)
- [x] 3.5 Manual check: after completing the walkthrough, the gateway's audit log shows all three calls with correct statuses — confirmed via the real `sutra-audit.db` produced by the task 2.3 run: `twin_chat` and `finanxe_get_snapshot` as single `executed` entries, `finanxe_set_debt_funding` as a `pending` entry followed by an `executed` entry, both sharing the same `pending_id`

All tests pass under `go test ./... -race`; `go build ./...` and `go vet ./...` are clean.
