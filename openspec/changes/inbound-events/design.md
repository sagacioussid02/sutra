## Context

`episode-graph-offers` introduced a signal intake so producers (weather,
calendar, idle research) could offer timely information. It works, but it
is a feature-local mechanism: untyped payloads in the offers store, one
consumer, no producer registry, no delivery semantics for anyone else.
Meanwhile the roadmap keeps adding event-shaped things — broker fills,
camera notifications, phone relays — each of which would otherwise invent
its own intake.

The gateway is already the project's front door: it owns auth, tool
tiers, and audit logging (`gateway-core`). The orchestrator already has
the pattern for consuming untrusted text safely (tool results, the
ask-first arbiter in `proactive-offers`, the isolated extractor in
`assistant-memory`).

## Goals / Non-Goals

**Goals:**
- One typed, durable, auditable way for the outside world to tell Sutra
  something happened.
- Producers identified and limited, like tools: a producer can only emit
  the kinds it is registered for.
- Consumers that are simple to write and safe to retry.
- Event text can never become an instruction, a memory, or a confirmation.

**Non-Goals:**
- Public webhooks or any new inbound exposure beyond the gateway's
  existing auth; no tunnel or port-forwarding story in this change.
- Exactly-once delivery or cross-producer ordering.
- Reacting to events with actions. Offers are the only reaction this
  change enables; actions keep their existing paths.
- A streaming/websocket bus. Store-and-drain is enough at this scale.

## Decisions

### The gateway takes intake; the orchestrator owns the log
Producers POST events to a gateway route, authenticated per producer.
The gateway validates envelope and registration, writes the audit entry,
and forwards to the orchestrator's event log (the same process boundary
the finanxe adapter already crosses). The orchestrator owns storage and
consumption.

*Why:* auth, tiers, and audit already live in the gateway; storage and
consumers already live in the orchestrator next to offers, reminders, and
memory. Putting the durable log in the gateway would split consumer state
across the boundary.

*Alternative considered:* producers write directly to a file or socket
the orchestrator watches. Rejected: no auth, no audit, and every producer
re-implements the envelope.

### Envelope, not free-form payloads
Kinds are declared in one registry module with a payload schema (field
names, types, size bound). Unknown kinds and oversize or malformed
payloads are rejected at intake, not at consumption.

*Why:* consumers can trust shape, and the payload bound keeps a noisy
producer from filling the log or a prompt. Schemas are deliberately
shallow (flat fields, short strings); an event is a notification, not a
document. Large content stays with the producer; the event carries a
reference.

### Store-and-drain with consumer cursors
One append-only `events` table; each consumer has a cursor row. Draining
returns events after the cursor in receive order; the consumer advances
the cursor after handling. A crashed consumer re-sees events
(at-least-once), so the consumer contract requires idempotent handling,
keyed on the event id and the producer's idempotency key when present.

*Why:* this matches how the reminders scheduler already treats firing
(exactly-once effect built on at-least-once delivery plus durable state),
and it keeps consumers decoupled: a new consumer starts from its own
cursor without touching producers.

### Expiry is part of the envelope
Every kind declares a default expiry and an event may set a shorter one.
Expired events are never delivered; the drain skips them and a periodic
sweep deletes them. This carries over the timely-offers rule that a snow
warning is never spoken after the snow.

### Trust rules, enforced in code
- Event payloads are passed to consumers labelled as untrusted data,
  through the same context-labelling the orchestrator uses for tool
  results.
- No code path from event intake to memory creation: the extractor in
  `assistant-memory` continues to see user utterances only.
- An event cannot carry a confirmation, an approval, or a tier change;
  the envelope has no field for them and consumers do not look for one.
- Urgency is a claim by the producer, not a fact: the arbiter still
  applies the producer allowlist for urgent treatment that
  `proactive-offers` defines.

### Per-source limits
Registration carries a rate (events per hour) and the log carries a
global cap; intake rejects over-limit events with a clear error and an
audit entry. A misbehaving producer degrades itself, not the assistant.

## Risks / Trade-offs

- [A producer floods the log] → per-source rate limits, payload bounds,
  global cap, expiry sweep.
- [Injected text in an event steers behaviour] → events are labelled
  untrusted, cannot create memories or confirmations, and reactions pass
  the ask-first arbiter unchanged.
- [A consumer wedges on a poison event] → drain advances past an event
  after a bounded number of failed attempts and records the failure, so
  one bad event cannot block the stream.
- [Duplicate delivery causes a duplicate offer] → consumers are
  idempotent on event id; the arbiter already allows at most one
  proactive item at a time.
- [The log grows quietly] → expiry sweep plus a size report in the
  control command; events are notifications, not history — episodes and
  memories remain the durable record.

## Migration Plan

The offers signal intake keeps its existing producer-facing shape behind
a shim that translates to envelopes of the corresponding kinds, so
current producers and the development signal-injection command keep
working. The shim is removed in a later cleanup once producers register
directly.

## Open Questions

- Should broker-fill events be produced by a shim polling the spy
  project's MCP server, or should that server grow an event hook? Decide
  with whoever owns that integration; the envelope supports either.
- Retention: is a short fixed retention (e.g. 30 days) acceptable for
  delivered events, or does the user want event history inspectable
  longer? Default in this change: delivered events kept 30 days.
