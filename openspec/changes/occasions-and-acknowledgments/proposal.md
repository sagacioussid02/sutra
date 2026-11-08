## Why

Sutra knows what time it is, but not what today *is*. For this family,
some days carry weight a clock cannot see: Diwali, a birthday, an
anniversary, a day of observance. A person who lives with you knows
"today is Diwali — puja is in the evening" without being told afresh
each year, and marks it the way people do: once, in passing, asking for
nothing. Sutra cannot. It has no record of the days this family
observes, and it has no category for a greeting that wants nothing
back. Its proactive machinery is all offers — proposals judged by the
arbiter, capped per day, waiting on a decision — so a zero-action
acknowledgment has nowhere to live. Bolting it onto offers would make
a greeting consume the user's offer budget, pass a judge that can
suppress it, and sit in the commitments list like a question nobody
answered.

This change gives Sutra an occasions store — days the user has
declared, with the context that makes them matter — and an
acknowledgment behaviour that is deliberately *not* an offer:
delivered at most once per occasion, attached to the first interaction
of the day, carrying no action and expecting no reply.

## What Changes

- **An occasions store, per user.** Each entry holds a name, a date
  rule (a single fixed date; an annual recurrence by month and day; or
  a lunar-calendar entry whose next occurrence date the user declares,
  with a note naming the calendar), a short context line, and
  observance notes ("puja in the evening", "fasting until sunset").
  Entries are declared by the user or confirmed by them — never
  scraped from a calendar, never inferred from behaviour.
- **Acknowledgment is its own category.** A zero-action social
  acknowledgment is not an offer: it never enters the ask-first
  arbiter, is not counted against the offer cap, is never deferred or
  judged, and creates no commitment. It is attached to the first
  ordinary interaction of the occasion's day — a line in passing at
  the head of a reply — and delivered at most once per occurrence. It
  is never a standalone interruption and never spoken out of nowhere;
  if the day passes with no interaction, it is not delivered late.
- **Follow-ons are offers, as usual.** Anything the occasion suggests
  doing — "want me to keep the evening clear?", proposing a reminder —
  goes through the normal offer and arbiter path as a separate offer,
  with its own effort estimate and cap accounting. The acknowledgment
  itself never books, blocks, reminds, or changes anything.
- **Occasions are part of world state.** An occasion occurring today
  registers as a field in the world-state snapshot (source: the
  occasions store; TTL: the end of the day), so the answerer, the
  offers judge, and a future planner can all see "Diwali today, puja
  in the evening" with its provenance, like any other field.
- **Principal state changes only by confirmation.** An observance note
  ("evening busy with puja") never silently edits the user's declared
  availability. If Sutra thinks an observance should shape the day, it
  offers the edit; only the user's confirmation writes it, through the
  same editing path `world-state` already defines.
- **Calendar packs are opt-in.** A bundled cultural calendar pack may
  be offered as a starting set, but it is off by default, copied into
  the user's own store when the user opts in, and editable and
  deletable like any declared entry. Nothing is acknowledged for a
  festival the user has not declared or adopted.
- Out of scope, deliberately: computing lunar dates from tables or
  external services (the user declares the next occurrence; a fetched
  calendar would be an inbound source needing its own approval),
  importing occasions from a calendar app, and reminding about
  occasions — a reminder is created through the normal offer path or
  by the user directly, not by the acknowledgment machinery.

## Capabilities

### New Capabilities
- `occasions-and-acknowledgments`: a per-user store of declared
  occasions with date rules, context, and observance notes, and a
  once-per-occurrence, zero-action acknowledgment attached to the
  day's first interaction

### Modified Capabilities
(none — world-state gains the occasion field through its existing
field registry, whose requirements already cover registered fields
generically; the offers arbiter's requirements are unchanged because
acknowledgments never enter it)

## Impact

- Orchestrator: a new `occasions` package (`db`, `store`, `service`,
  `commands`) following the `life` and `offers` layout; a delivery
  check at turn start in `Orchestrator.respond`, where the world-state
  snapshot is assembled; a `SUTRA_OCCASIONS` switch documented in
  `orchestrator/.env.example` like every other `SUTRA_*` setting.
- Storage: one more per-user SQLite store with the memory stores'
  protections (schema-versioned, file permissions 0600). No gateway,
  twin, or finanxe changes.
- Reads: the world-state field registry (this change registers the
  occasion field). Writes to principal state: none directly — only
  through confirmed offers, using the editing path `world-state`
  already provides.
- Depends on `per-user-identity` (an occasion is always exactly one
  user's) and on `world-state` (the field registry, and the snapshot
  assembled at turn start is where "today" is decided).
