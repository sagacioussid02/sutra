## Why

Sutra today only learns about the world when the user speaks to it. Things
that matter happen in between: a camera sees someone at the door, a broker
order fills, a calendar event moves, a phone notification arrives. The one
inbound path that exists — the signal intake built for timely offers in
`episode-graph-offers` — is narrow: it lives in the offers store, serves
one consumer, and has no general transport, typing, or delivery rules
other features can build on.

An assistant that should notice things needs a real front door for events,
with the same safety posture as everything else in this project: events
are untrusted data, producers are identified and limited, and anything an
event leads to still passes the existing ask-first and confirmation
machinery. This is a foundation change: `world-state` reads fresher
inputs from it, and later hardware (cameras, sensors) plugs into it.

## What Changes

- **A typed event envelope.** Every event carries an id, a registered
  source, a kind, `occurred_at` and `received_at`, the user it belongs to
  (attributed via `per-user-identity`), a bounded payload whose shape is
  declared per kind, an optional idempotency key, and an expiry.
- **A registered-producer intake on the gateway.** Producers authenticate
  with their own bearer token and may only emit the kinds they are
  registered for, mirroring how tools are tiered at registration.
  Registration is configuration, not code.
- **A durable event log.** Events land in a local, owner-only SQLite log.
  Consumers (the offers arbiter first) drain it with per-consumer cursors;
  delivery is at-least-once, so consumers are idempotent. Events are
  dropped silently after their expiry, as timely offers already are.
- **The offers signal intake migrates onto it.** `proactive-offers`
  consumes events of the kinds it already accepts, through a compatibility
  shim, so existing producers and tests keep working.
- **Events are data, never instructions.** Event payload text is untrusted
  exactly like tool results: it cannot create a memory directly, cannot
  confirm or approve anything, cannot change a tool tier, and cannot raise
  its own priority. A proactive reaction to an event goes through the
  ask-first arbiter with its existing caps and blocks; anything that would
  act, spend, or change state still ends at a normal confirmation.
- Out of scope, deliberately: public-internet webhooks (producers are
  local or LAN-reachable through the gateway's existing auth), delivery to
  a machine that is powered off, guaranteed ordering between producers,
  and any autonomous action taken on an event beyond an offer.

## Capabilities

### New Capabilities
- `inbound-events`: registered producers emit typed, expiring events into a durable log that orchestrator consumers drain under the project's untrusted-data rules

### Modified Capabilities
(none — `proactive-offers` consumes the new intake through a shim; its requirements are unchanged)

## Impact

- Gateway: a new intake route, a producer registry in configuration, and
  audit entries for accepted and rejected events.
- Orchestrator: a new `events` package (envelope, log store, drain,
  consumer registry) following the reminders/offers layout, with a local
  `events.db` (owner-only, gitignored).
- Attributes each event to the producer's configured owner (single-owner;
  `per-user-identity` is deferred and will later supply the mapping), and
  depends on `gateway-core` (auth, tiers, audit). Consumed by `proactive-offers`
  first; `world-state` and later hardware changes build on it.
- No twin, finanxe, or minions changes. Existing projects are not modified
  to emit events; producers are small new shims owned by whoever runs them.
