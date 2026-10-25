## Context

None of the user's projects (twin, finanxe, or the others) have any
existing OpenAPI, MCP, or manifest/capability-description mechanism today
(confirmed by direct inspection) — this is invented from scratch,
deliberately minimal so it's trivial to implement in a stdlib Python
server, a FastAPI app, or anything else with an HTTP endpoint.

This sits alongside `mcp-tools-twin` and `mcp-tools-finanxe-*`, not on top
of them: twin's session derivation and finanxe's debt-name matching are
real business logic a generic HTTP caller can't express, so those adapters
stay hand-written. Discovery is the onboarding path for tools that *are*
plain REST calls, and for future projects that don't have a hand-written
adapter yet.

## Goals / Non-Goals

**Goals:**
- A human never has to read a new project's source to find out what tools
  it could expose to the gateway.
- Nothing a discovered project offers becomes callable without an explicit,
  per-tool human decision — including the tier it runs at.
- An approved, REST-shaped tool becomes a real, working gateway tool
  without new Go code.

**Non-Goals:**
- No background/auto-polling discovery — always a manually run
  `sutra-discover`, consistent with how every other side-effecting or
  trust-sensitive action in this project is an explicit human action, not
  an ambient background process.
- No hot-reload — approved tools go live on the next gateway restart, same
  as every other config change today (`tokens.yaml`, `discovery-sources.yaml`).
- No path-parameter interpolation in manifest `path` (e.g. `/api/debts/{id}`)
  in v1 — every existing hand-written tool already avoids this shape (ids
  travel in the query string or JSON body instead), so this is a scope cut,
  not a blocker. A natural v2 extension once a project actually needs it.
- No signature or auth handshake on manifest fetch — trust is established
  entirely by the human approval step, not by anything cryptographic.

## Decisions

- **Manifest convention**: `GET /.well-known/sutra-agent.json`, a small
  JSON document (`sutra_manifest_version`, `project{name,description}`,
  `tools[]`). Each tool declares `name`, `description`, `tier_hint`,
  `method`, `path`, `args[]` (`name`, `type`, `required`, `secret`, `in`:
  `query`|`body`), and `generic_callable` (+ `generic_callable_reason` when
  false). See `docs/agent-manifest.md` for the full spec and
  `docs/examples/finanxe.sutra-agent.json` for a worked example covering
  both a generic-callable tool and a bespoke one.
- **`tier_hint` is never trusted.** A manifest is written by the project
  being discovered, not by the gateway's operator — it's a suggestion the
  human approver sees, never something fed directly into `registry.Tier`.
  The approval CLI requires the human to *type* the tier they want, not
  accept the hint with one keystroke, and prints a loud warning (requiring
  the tool name to be re-typed to proceed) if a `POST`/`PUT`/`PATCH`/`DELETE`
  tool is being approved as `read-only` — a soft nudge against the most
  likely careless mistake, not a hard technical guarantee.
- **Approval is a durable, per-`(source, tool)` decision**, stored in a new
  SQLite store (`internal/discovery`, same `Open`/`Store` shape as
  `internal/confirm`), keyed by a content hash of the tool's manifest
  entry. A tool whose live manifest hash no longer matches what was
  approved is treated as *not currently approved* — it silently stops
  being registered at the next startup until a human re-runs
  `sutra-discover` and re-approves it. This is the safe default: never
  silently keep serving an old approval against new behavior, and never
  silently adopt new behavior unreviewed.
- **Rejections aren't permanent state that hides a tool** — a rejected
  tool is resurfaced on every future discovery run (the human can change
  their mind), rather than requiring a separate "unreject" flow.
- **Generic auto-wiring only covers REST-shaped, side-effect-simple tools.**
  `internal/genericadapter` builds a `registry.Definition` from a
  manifest tool's method/path/args, reusing `registry.Redact` (already
  generic by key name — confirmed from `redact.go`) for secret-arg
  handling and gateway-core's existing confirm-first flow for anything
  tiered `confirm-first`. A `generic_callable: false` tool is recorded as
  approved (with its tier) but is *not* registered — it needs a
  hand-written adapter in the same shape as `twin.go`/`finanxe.go` before
  it can actually be called. Approval and "is callable" are deliberately
  separate facts.
- **A name collision between a generically-registered tool and an
  existing hand-written one is expected, not an error worth crashing
  over** — e.g. if finanxe later serves a manifest that also describes
  `finanxe_list_debts`. `cmd/gateway/main.go` registers hand-written
  adapters first; `genericadapter.RegisterApproved`'s own per-tool
  registration failures (including "name already registered") are logged
  and counted as skipped, never fatal to gateway startup.
- **`sutra-discover` is a separate binary from `sutra-cli`.** `sutra-cli`
  is documented as a pure MCP network client with no gateway-internals
  access; `sutra-discover` runs locally and reads/writes the discovery
  SQLite store directly, so it has to be a distinct process with
  filesystem access to the gateway's own data directory.

## Risks / Trade-offs

- The tier-hint trust boundary is enforced by requiring an explicit typed
  decision plus a warning nudge, not by anything that can't be typed past
  carelessly. Acceptable for a "me + a few trusted users" personal system
  where the approver is also the gateway operator; would need real policy
  enforcement before this pattern could extend to a less trusted approver.
- A backend that's unreachable when the gateway starts causes that
  source's discovered tools to simply not be registered for that run
  (logged, not fatal) — favors "the gateway always starts" over "approved
  tools are always present," matching how finanxe/twin's own per-call
  errors already favor availability of the gateway itself over any one
  backend.
