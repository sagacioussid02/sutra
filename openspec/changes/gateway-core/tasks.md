## 1. Project scaffold

- [x] 1.1 Create `gateway/` Go module (`cmd/gateway`, `internal/...`) with deps on `github.com/modelcontextprotocol/go-sdk` and `modernc.org/sqlite`
- [x] 1.2 Add local config loading (gitignored `tokens.yaml`; documented shape in `tokens.example.yaml`)
- [x] 1.3 Add `.gitignore` entries for the token file and the SQLite audit/pending-confirmation databases

## 2. Tool registry and tiers

- [x] 2.1 Implement the tool registry: `Register(*Definition)` with name, handler, tier, secret arg names, describe func (`internal/registry`)
- [x] 2.2 Enforce tier is required and one of `read-only` / `confirm-first` / `never-by-voice` at registration time
- [x] 2.3 Filter `never-by-voice` tools out of the MCP tool list (`Registry.Callable()`), while keeping them reachable via `Lookup` for future use
- [x] 2.4 Wire immediate execution path for `read-only` tools (`gateway.readOnlyHandler`)

## 3. Authentication

- [x] 3.1 Implement bearer token extraction and validation — via the official SDK's `auth.RequireBearerToken` middleware, backed by `authcfg.Config.Verifier()`
- [x] 3.2 Implement token -> user id -> allowed-tools resolution (`authcfg.Config`)
- [x] 3.3 Enforce allowed-tools check before dispatching any tool call (`gateway.authorizationMiddleware`, an `mcp.Middleware` via `AddReceivingMiddleware`)
- [x] 3.4 Missing/invalid bearer tokens are rejected uniformly (HTTP 401) by the SDK's auth middleware, before any tool name is even parsed; not-authorized-for-a-specific-tool is a distinct, audited denial one layer up, inside the MCP method middleware — see design.md's note on why pre-auth failures aren't tool-attributed in the audit log

## 4. Confirmation flow

- [x] 4.1 Implement pending-confirmation store (SQLite) with id, user id, tool name, args, created_at, expires_at, status (`internal/confirm`)
- [x] 4.2 On `confirm-first` tool call: create pending record, return id + human-readable description, do not execute (`gateway.confirmFirstHandler`)
- [x] 4.3 Implement `gateway_confirm(pending_id)` operation: validate ownership, non-expiry, not-already-used (atomically), then execute original call (`confirm.Store.Claim`, `gateway.gatewayConfirmHandler`)
- [x] 4.4 Implement TTL expiry check and configuration (`confirm.DefaultTTL` = 5 min, overridable via `-confirm-ttl`)

## 5. Audit log

- [x] 5.1 Create `audit_log` SQLite table per design.md's schema (`internal/audit`)
- [x] 5.2 Write an audit entry on every denial, pending-creation, confirmation-execution, direct-execution, and error path
- [x] 5.3 Implement argument redaction using each tool's declared secret argument names (`registry.Redact`)
- [x] 5.4 Add a query helper (by user, tool, status, time range) for later CLI/inspection use (`audit.Store.Find`)

## 6. Verification

- [x] 6.1 Register placeholder read-only (`echo`), confirm-first (`mutate`), and never-by-voice (`secret`) tools in `internal/gateway`'s test suite
- [x] 6.2 Test: unauthenticated call is rejected (HTTP 401, `TestMissingTokenIsRejected`/`TestInvalidTokenIsRejected`); an authenticated-but-not-allowed call is denied and logged (`TestUnauthorizedToolCallIsDeniedAndLogged`)
- [x] 6.3 Test: authorized read-only call executes and is logged (`TestReadOnlyToolExecutesImmediately`)
- [x] 6.4 Test: confirm-first call is held (handler does not run), then confirmed successfully; pending and executed audit entries present, linked by pending id (`TestConfirmFirstToolIsHeldThenConfirmed`)
- [x] 6.5 Test: expired confirmations rejected (`confirm.TestClaimAfterExpiryFails`); double-used and concurrent double-claims rejected (`confirm.TestClaimTwiceFailsSecondTime`, `TestConcurrentClaimsOnlyOneSucceeds`, `gateway.TestConfirmFirstToolIsHeldThenConfirmed`'s re-confirm check)
- [x] 6.6 Test: never-by-voice tool does not appear in `ListTools` and is not dispatchable by name (`TestNeverByVoiceToolIsNotListedOrCallable`)
- [x] 6.7 Test: secret arguments are redacted in audit log entries (`registry.TestRedactMasksOnlyDeclaredSecrets`, `gateway.TestConfirmFirstToolIsHeldThenConfirmed`'s pending-entry redaction check)

All tests pass under `go test ./... -race`; `go build ./...` and `go vet ./...` are clean.
