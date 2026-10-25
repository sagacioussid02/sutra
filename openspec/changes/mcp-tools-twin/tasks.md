## 1. Verify twin's auth requirements

- [x] 1.1 Read `get_current_user_id`/`get_current_user_email` dependency implementations in `twin/backend/server.py` to confirm whether `/chat` accepts anonymous/session-based calls or strictly requires a Clerk JWT — confirmed: `/chat`'s `credentials` param is `Optional`, `_decode_user_claims` tolerates missing/absent credentials, and the anonymous path (client-supplied `session_id`, `PUBLIC_PERSONA_ANON_LIMIT`) is fully supported. `/public-personas` and `GET /twin/{id}` require no auth at all.
- [x] 1.2 Based on 1.1, confirm whether per-gateway-user session mapping (design.md's primary plan) or a shared service identity (fallback) applies — neither: the adapter calls `/chat` anonymously and derives its own stable `session_id` per (gateway user, twin id), passed as the client-supplied `session_id` twin's anonymous path already expects. No Clerk JWT or shared service identity needed.

## 2. Adapter implementation

- [x] 2.1 Add twin base URL and any needed service credential to gateway config (`-twin-base-url` flag, defaulting to the deployed API; `-twin-session-secret` / `$TWIN_SESSION_SECRET` optional HMAC secret) — `gateway/cmd/gateway/main.go`
- [x] 2.2 Implement `_derive_session_id(gateway_user_id, twin_id)` matching twin's own derivation pattern — `Client.deriveSessionID` in `gateway/internal/twin/twin.go` (HMAC-SHA256 if a secret is configured, else plain SHA-256, mirroring twin's own dev fallback)
- [x] 2.3 Implement `twin_chat(twin_id, message)` calling `/chat`, mapping twin's response to the tool result — `Client.Chat`
- [x] 2.4 Implement `twin_list_public_personas()` calling `/public-personas` — `Client.ListPublicPersonas`
- [x] 2.5 Handle twin API errors (not found, 5xx, timeout) as tool-level errors, not gateway crashes — `Client.Chat`/`ListPublicPersonas` return wrapped errors on non-200 status, decode failure, or request/timeout failure; never panic

## 3. Registration

- [x] 3.1 Register both tools as `read-only` with `gateway-core`'s tool registry — `twin.Register` in `gateway/internal/twin/twin.go`, wired in `cmd/gateway/main.go`
- [x] 3.2 Add both tools to at least one trusted user's allowed-tools set in the (gitignored) token config example — already present in `tokens.example.yaml`

## 4. Verification

- [x] 4.1 Test: `twin_chat` against a real or mocked twin endpoint returns a reply — `TestChat_ReturnsReply`
- [x] 4.2 Test: repeated calls from the same gateway user reuse the same derived session id — `TestChat_SameUserSameTwin_ReusesSessionID`
- [x] 4.3 Test: unknown twin id produces a tool-level error, not an unhandled exception — `TestChat_UnknownTwinID_ReturnsToolError`
- [x] 4.4 Test: `twin_list_public_personas` returns the persona list — `TestListPublicPersonas_ReturnsList`
- [x] 4.5 Manual check: both tool calls appear correctly in the gateway's audit log — verified via a throwaway integration test wiring `twin.Register` + `audit.Store` together; both `twin_chat` and `twin_list_public_personas` wrote correct entries (tool name, tier, args, result) before the scratch test was deleted

All tests pass under `go test ./... -race`; `go build ./...` and `go vet ./...` are clean.
