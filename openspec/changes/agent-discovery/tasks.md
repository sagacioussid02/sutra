## 1. Manifest spec and docs

- [x] 1.1 Write `gateway/docs/agent-manifest.md`: the Sutra Agent Manifest v1 spec (convention, JSON shape, field meanings, explicit "`tier_hint` is a suggestion, not trusted" note) plus the project onboarding runbook (add a route, add a source, run `sutra-discover`, review/tier, hand-write an adapter for non-generic tools, add to `tokens.yaml`, restart)
- [x] 1.2 Write `gateway/docs/examples/finanxe.sutra-agent.json`: a worked reference manifest covering a generic-callable tool (`list_debts`) and a bespoke one (`set_debt_funding`, `generic_callable: false` with a reason) — reference only, not wired live

## 2. `internal/manifest`

- [x] 2.1 Define `Manifest`, `Project`, `Tool`, `Arg` (with `ArgType`, `ArgLocation`) types matching the spec in 1.1
- [x] 2.2 Implement `Fetch(ctx, *http.Client, url) (*Manifest, error)` — same error-wrapping discipline as `finanxe.go`'s `get` (connection/status/decode failures become wrapped errors, never panics)
- [x] 2.3 Implement `(*Manifest) Validate() error` — required fields present, recognized `method`/`type`/`in` values, unique tool names; collects every problem rather than stopping at the first
- [x] 2.4 Implement `(Tool) Hash() string` — stable content hash (sha256 over the tool's JSON encoding) of a tool's full definition, used to detect a changed manifest entry

## 3. `internal/discovery`

- [x] 3.1 Implement the SQLite-backed `Store` (`Open`, `Close`) with the `discovery_approvals` table, following `internal/confirm`'s `Open`/`SetMaxOpenConns(1)` pattern
- [x] 3.2 Implement `Store.Record(ctx, Approval)`, `Store.Get(ctx, source, tool)`, `Store.Approved(ctx) ([]Approval, error)`
- [x] 3.3 Implement `Diff(ctx, *Store, *manifest.Manifest) ([]PendingReview, error)` classifying each tool as new / changed / unchanged against the store, resurfacing previously rejected tools rather than hiding them

## 4. `internal/genericadapter`

- [x] 4.1 Implement `Client` and `call(ctx, manifest.Tool, args)` — query-string args for `in: query`, JSON body for `in: body` (mirroring `finanxe.go`'s `get`/`postJSON`); validate required args are present and roughly type-matched, rejecting with a tool-level error otherwise
- [x] 4.2 Implement `BuildDefinition(client, sourceName string, tool manifest.Tool, tier registry.Tier) (*registry.Definition, error)` — name `sourceName_toolName`, `SecretArgs` from `tool.Args` where `secret: true`, a generic `Describe` for `confirm-first` tools built from the tool's description and args
- [x] 4.3 Implement `RegisterApproved(reg, sourceName, client, tools, approvals) (registered, skipped int)` — registers only approved + `generic_callable` + hash-matching tools; treats `reg.Register` failures (including name collisions with a hand-written adapter) as non-fatal, counted as skipped

## 5. `cmd/sutra-discover`

- [x] 5.1 Add `gateway/discovery-sources.example.yaml` (checked in) documenting the sources config shape (`name`, `manifest_url`, `base_url`); gitignore the real `discovery-sources.yaml`
- [x] 5.2 Implement the CLI: fetch + validate a manifest (single `-url` or all of `-sources`), run `discovery.Diff`, and for each new/changed tool print its details (explicitly labeling `tier_hint` as "suggested, not trusted") and prompt for a typed tier / `reject` / `skip`
- [x] 5.3 Implement the mistier safety nudge: a `POST` tool being approved as `read-only` triggers a warning and requires re-typing the tool name to proceed (manifest methods are restricted to GET/POST by `Validate`, so PUT/PATCH/DELETE never arise here)
- [x] 5.4 Record each decision via `discovery.Store.Record`; print a closing summary and a reminder that a gateway restart is required for newly approved tools to go live

## 6. Gateway startup wiring

- [x] 6.1 Add `-discovery-db` and `-discovery-sources` flags to `cmd/gateway/main.go`
- [x] 6.2 Open the discovery store and load sources via the new `internal/discoverysrc` package (tolerates a missing `discovery-sources.yaml` — discovery is optional)
- [x] 6.3 For each configured source: fetch its manifest (log-and-skip that source on failure, never fatal to gateway startup), then call `genericadapter.RegisterApproved`, logging tools registered/skipped per source

## 7. Verification

- [x] 7.1 Test: `internal/manifest` — fetch/parse/validate against an `httptest.Server`, including malformed-manifest cases; `Hash` is stable across repeated calls on the same tool and differs when any field changes
- [x] 7.2 Test: `internal/discovery` — store CRUD, and `Diff`'s new/changed/unchanged classification, including a rejected tool being resurfaced
- [x] 7.3 Test: `internal/genericadapter` — `call`'s query-vs-body routing, required-arg validation, error wrapping on non-2xx/connection failure, and that a registered generic tool's declared secret args are populated onto `Definition.SecretArgs` (redaction itself is gateway-core's existing, already-tested mechanism, which applies identically regardless of a tool's origin)
- [x] 7.4 Test: `RegisterApproved` skips a `generic_callable: false` approval, skips a hash-mismatched (stale) approval, skips an approval for a different source, and treats a name collision with an already-registered tool as non-fatal
- [x] 7.5 Manual check: served the reference `docs/examples/finanxe.sutra-agent.json` (project renamed to `finanxe-demo` to avoid an intentional collision with the real hand-written finanxe adapter) from a local test server, ran `sutra-discover` against it, approved `list_debts` as read-only and `set_debt_funding` as confirm-first (exercising and confirming the mistier safety nudge on the latter, a POST tool), rejected it on a second pass to also exercise rejection. Restarted a real test gateway: `finanxe-demo_list_debts` appeared in `sutra-cli`'s tool list, returned real data end-to-end through the generic adapter with zero hand-written Go code, and was correctly audited (`read-only`/`executed`); `finanxe-demo_set_debt_funding` never appeared, and the real `finanxe_list_debts` name collision was confirmed non-fatal (hand-written adapter wins, generic registration silently skipped) exactly as designed
- [x] 7.6 `go build ./...`, `go vet ./...`, `go test ./... -race` clean across the whole module (12 packages, all passing)
