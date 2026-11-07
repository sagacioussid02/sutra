## Context

Sutra's picture of "now" is scattered: the calendar lives behind finanxe
tools, commitments live in the reminders, offers, and confirmation
machinery, the episode graph holds what was discussed and left open, and
memory holds durable facts that may or may not still hold. `direct-answers`
established the rule that volatile facts need a fresh check, but each
feature re-implements its own check and its own idea of "fresh".

This change is a read model, not a new store: one assembly point that
asks each existing source for its current value, stamps it, and hands
consumers a single object whose honesty about age is the whole point.

## Goals / Non-Goals

**Goals:**
- One snapshot consumers share, instead of per-feature re-derivation.
- Every field labelled with source and observed-at; staleness visible.
- Cheap: assembly on turn start must not add noticeable latency or a
  pile of tool calls.
- A field that cannot be observed is absent, and its absence is visible.

**Non-Goals:**
- A continuously updated cache or background poller.
- Precise location. Presence is a coarse hint the user can see and set
  ("home", "out", "do not disturb"), never GPS-derived in this change.
- Storing financial figures. The finance field points at the latest
  finanxe snapshot; figures are fetched through the tools when a reply
  actually needs them, so numbers are never quoted from a stale copy.
- Predicting the future state (traffic later, calendar conflicts next
  week). The snapshot is now, plus what is already scheduled.

## Decisions

### Assemble on turn start, cache in memory for the TTL
The provider assembles lazily at the first read in a turn and reuses the
result for that turn. Between turns it keeps nothing except an in-memory
cache bounded by the shortest field TTL. No database, no daemon.

*Why:* freshness requirements here are minutes, not milliseconds, and a
durable cache would become one more store that can quietly go stale —
the failure this change exists to prevent.

*Alternative considered:* assemble in the background on a timer.
Rejected: it spends tool calls when nobody is asking, and its output is
still a cache with an age — the same object, at higher cost.

### A field registry carries the TTLs
Each field is registered with its source, TTL, and renderer. Indicative
TTLs: presence hint, until changed (user-set, so age is shown but it does
not expire); calendar now/next, 5 minutes; open commitments, 1 minute
(they change when the user acts); finance pointer, 15 minutes; fresh
events, the events' own expiries. TTLs are configuration, documented in
`.env.example` like every other `SUTRA_*` setting.

### Stale is a presentation, not an error
Rendering shows age inline and marks fields past TTL as stale rather
than dropping them silently, because "calendar as of 40 minutes ago" is
often still useful — as long as nobody mistakes it for now. Structured
consumers get the same data: value, source, observed-at, stale flag.
Code that needs a guaranteed-fresh field (for example before a
confirm-first action) can demand a max age and force re-assembly of that
field only.

### Commitments come from the machines that own them
Pending confirmations, unanswered offers, active reminders, and graph
open items are read from their existing stores at assembly time. The
snapshot does not track or resolve them; it reports them, so a planner
or a reply can see "one offer is still open" before layering on another.

### Per-user by construction
Assembly takes the user id from the `per-user-identity` mapping and reads
only that user's stores and tool views. There is no multi-user snapshot
and no field that mixes users.

## Risks / Trade-offs

- [Assembly latency on turn start] → per-source timeouts with absence on
  failure, in-turn caching, and a bounded prompt block; slow sources
  degrade to missing fields, not slow turns.
- [A stale field is trusted anyway] → age is rendered inline in the text
  the model sees, and the stale flag is part of the structured value;
  tests cover a model-facing render with an expired field.
- [Snapshot becomes a shadow database] → no persistence in this change,
  pointers instead of copies for finance, and a design rule that a field
  must name the store that owns its truth.
- [Presence hint leaks into wrong contexts] → the hint is user-set,
  coarse, shown in the control surface, and included in the snapshot
  only for the user's own session.

## Migration Plan

Consumers adopt the snapshot one at a time: the offers judge first (it
already assembles a similar picture by hand), then `direct-answers`.
Until a consumer adopts it, nothing changes for that consumer. The
hand-rolled assembly in the offers judge is deleted when its adoption
lands, not before.

## Open Questions

- Should the finance pointer include the headline total-debt figure as
  of its snapshot time, or strictly a pointer? Design says pointer only;
  revisit if replies keep making a second call for the same number.
- Presence: is a manual hint enough, or should the voice client's
  activity state (in a conversation, idle) feed it automatically? Leaning
  yes for client activity, no for anything location-like.
