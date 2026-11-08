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
- Consumers can shape what they ask of the user to the user's declared
  capacity, not only to Sutra's own budgets.

**Non-Goals:**
- A continuously updated cache or background poller.
- Precise location. Presence is a coarse hint the user can see and set
  ("home", "out", "do not disturb"), never GPS-derived in this change.
- Storing financial figures. The finance field points at the latest
  finanxe snapshot; figures are fetched through the tools when a reply
  actually needs them, so numbers are never quoted from a stale copy.
- Predicting the future state (traffic later, calendar conflicts next
  week). The snapshot is now, plus what is already scheduled.
- Inferring the user's capacity from behaviour. Principal state is
  declared by the user or confirmed by them; nothing is derived from
  watching them, and no calendar is scraped for it in this change.

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

### What changed during implementation
- The finance pointer is "when the finance snapshot tool was last read this
  session", because finanxe's snapshot carries no timestamp. If never read, the
  field is absent.
- The presence hint is in memory only: after a restart it is not known, never
  guessed. Values are a fixed set (home, out, busy, do-not-disturb).
- Only the calendar (a tool call) is cached for its TTL; local reads are always
  fresh, so a reminder created a moment ago shows at once.
- The calendar read honours the current safety mode and authentication, the
  same as a model-requested tool call would. A user-per-snapshot mapping uses
  the single owner until `per-user-identity` lands.
- The judge's own context was never hand-assembled for commitments or presence,
  so it simply gains the snapshot block.

### Principal state is part of the snapshot, and declared only
The registry gains a principal section describing the user's capacity,
with the same source / observed-at / TTL treatment as every other
field:

- **Availability windows** — when the user is open to being asked
  things. Until changed, like the presence hint: age is shown, it does
  not expire.
- **Attention budget** — a coarse daily allowance in minutes for
  assistant asks (offers, questions, reviews). Until changed.
- **Major commitments** — user-declared entries with end dates ("house
  closing, mid-December"), recorded exactly as stated. A commitment is
  current until its end date and stale after it; it is never extended
  by inference.
- **Effort sensitivity** — a preference for how Sutra should bias when
  the budget runs low (for example: prefer work it can finish itself,
  asynchronously, over work that bills the user). Until changed.

The only sources are explicit: user-declared settings and entries the
user has confirmed. There is no inference of capacity from behaviour —
not from response latency, not from ignored offers, not from activity
patterns — and no calendar scraping in this change. A calendar-derived
source would be a later, separately approved capability; if it ever
lands, it enters through the same registry as a named source, not as a
silent upgrade of a declared field.

Principal state is the one thing the snapshot reads that is not owned
by an existing machine: it is the user's own declaration, held in a
small per-user store with the memory stores' protections (local
SQLite, schema-versioned, file permissions 0600). The snapshot remains
a view — it persists nothing; it reads the declaration at assembly
time like it reads any other store.

### Effort rides on the offer
The ask-first arbiter attaches an estimated user-effort to every offer
it considers: minutes, plus the kind of effort — a decision, a review,
or hands-on work. Kinds matter because they are not interchangeable:
ten minutes of hands-on work inside an unavailable window costs the
user more than a two-minute decision inside an open one.

An offer whose estimate exceeds the user's remaining budget for the
day is deferred, not dropped: the offers store records it as deferred
with the reason, the control surface shows deferred offers, and the
snapshot's commitments field counts them, so a deferral is visible
rather than a silent disappearance. A deferred offer is reconsidered
when the budget frees up — a new day resets the allowance, a major
commitment reaching its end date frees the capacity it was holding —
and presenting it still passes the existing gates, including the
four-a-day cap, which applies on top of the budget and independently
of it.

Timed proposals respect declared availability: an offer or reminder
whose natural moment falls inside an unavailable window is scheduled
outside it, the same way quiet hours already work for spoken delivery.

### The planner prices the user's time
When a planner (this change's consumers include any future one)
decomposes work into steps, it prices each step in two currencies:
Sutra's own cost, which the existing budgets already govern, and the
user's time. Between two decompositions that are otherwise equal, it
prefers the one whose steps Sutra can complete autonomously within its
granted autonomy. When a step does bill the user — a decision only the
user can make, a review, hands-on work — the plan states the expected
user-effort where the plan is presented, in the same minutes-and-kind
terms as an offer. A plan that quietly assumes an evening of the
user's time is a mispriced plan, and mispricing is treated as a defect
in the plan, not a surprise for the user.

### Absent principal state changes nothing
Principal state is an input, never a prerequisite. If the user has
declared nothing, or every principal field is stale, consumers behave
exactly as they do today: the offer cap alone governs offers, plans
carry no effort statements, timing follows existing rules. Stale
principal fields render as stale in the snapshot and are treated as
absent for budgeting — a budget declared for a life the user is no
longer living must not silently govern what they are asked. Nothing
blocks a turn, an offer, or a plan on missing principal state.

### Principal state is the user's data
Every principal field can be viewed and edited by the user it
describes: the `/state` control surface shows the principal section
exactly as consumers see it, and control commands change each field.
Edits take effect at the next assembly. Principal state never appears
in another user's snapshot, is never shared across users, and is never
an input to another user's offers or plans.

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
- [Declared principal state drifts from real life] → commitments carry
  end dates and expire on them, budget and availability show their age
  and are one command to change, and staleness falls back to today's
  defaults rather than to a wrong budget.
- [Effort estimates are rough] → estimates are deliberately coarse
  (minutes, three kinds); the cost of a wrong estimate is a visible,
  overridable deferral — never a lost offer or a blocked plan.

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
- Should observed offer outcomes (accepted, finished in two minutes)
  calibrate future effort estimates? Leaning no in this change —
  calibration is inference about the user and waits for its own
  approval, like any other inferred field.
