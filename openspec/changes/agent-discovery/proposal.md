## Why

Phase 1 wrapped exactly two backend projects (twin, finanxe) by hand — reading
each project's source directly, then hand-writing a Go adapter
(`internal/twin`, `internal/finanxe`) with one `registry.Definition` per
tool. That doesn't scale to the user's other projects (a trading agent, a
journaling-shaped project, and at least one more) or to any future project,
and it means a human has direct code access to every backend just to onboard
it. The user wants sutra to be able to find out what a new backend project
offers, and to make a tool callable only once they've explicitly approved
it — with approval actually producing a working tool, not just a list
someone still has to hand-code.

## What Changes

- Define a small, framework-agnostic **manifest** any backend project can
  serve (`GET /.well-known/sutra-agent.json`) describing its own tools:
  name, description, an untrusted tier *hint*, HTTP method/path/args, and
  whether it's safely callable by a generic HTTP adapter or needs a
  hand-written one.
- Add a `sutra-discover` CLI that fetches a project's manifest, shows the
  user every new or changed tool, and requires an explicit human decision
  (a typed tier, `reject`, or `skip`) before anything is recorded as
  approved. Nothing is ever called during discovery itself.
- Add a generic HTTP-calling adapter that turns an approved,
  generically-callable manifest tool into a working `registry.Definition`
  at gateway startup — auto-wired, no new Go code required for
  straightforward REST-shaped tools.
- Tools whose manifest entry is marked not generically callable (like
  finanxe's name-resolving `set_debt_funding`) are still discovered and
  approved/tiered, but stay unregistered until a human writes a bespoke
  adapter for them — approval alone isn't enough for those, by design.
- Document the manifest spec and a project onboarding runbook, so adding a
  6th/7th/Nth project doesn't require reading its source by hand.

## Capabilities

### New Capabilities
- `agent-discovery`: manifest-based discovery of a backend project's tools,
  a human approval workflow that gates registration (never execution), and
  generic auto-wiring of approved, REST-shaped tools

### Modified Capabilities
(none — this adds a second, generic onboarding path alongside the existing
hand-written twin/finanxe adapters; it does not change `gateway-core`,
`twin-mcp-tools`, `finanxe-readonly-tools`, or `finanxe-mutating-tools`)

## Impact

- New packages only (`internal/manifest`, `internal/discovery`,
  `internal/genericadapter`), a new `cmd/sutra-discover` binary, and one
  more block in `cmd/gateway/main.go`'s existing startup sequence — no
  changes to `gateway-core`'s auth/tiering/confirm/audit guarantees, which
  apply identically to a generically-registered tool as to a hand-written
  one.
- No changes to twin or finanxe themselves in this change — a reference
  example manifest is documented for finanxe, but finanxe is not required
  to actually serve it for this change to be complete; onboarding a real
  new project is a follow-up, not blocked by this change.
- Requires each future project to add roughly 5 lines (a `/.well-known/`
  route or static file) to opt into discovery — no change is invisible or
  automatic on the project side.
