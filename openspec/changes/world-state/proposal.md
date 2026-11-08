## Why

Before acting, Sutra re-derives "what is true right now" from scratch, or
worse, answers from memory. `direct-answers` handles one slice of this —
volatile facts need a fresh check — but every feature does it its own way:
the offers judge reads the episode graph, reminders know their own queue,
the finanxe tools know the money picture, and none of it is in one place
with an honest age attached. The result is an assistant that can say
"you're free this afternoon" off a calendar it read an hour ago, or plan
around a commitment it has forgotten is still open.

A world-state layer gives every consumer — the answerer, the offers
judge, and later a planner — one snapshot of the user's current situation
where every field carries its source and the time it was observed, and
where stale is visible as stale instead of silently trusted.

## What Changes

- **A snapshot assembled on demand.** At turn start (and on explicit
  refresh), a provider assembles a snapshot for the current user from
  sources that already exist: presence hint (user-set, or derived from
  the active client), calendar now/next from the finanxe-style calendar
  tools, the latest finance headline as a *pointer* (which snapshot, when
  taken — not a copied figure), open commitments (pending confirmations,
  unanswered offers, active reminders, open items from the episode
  graph), and the freshest inbound events relevant to now.
  Principal state (the user's declared availability, attention
  budget, and current major commitments) is one of the assembled
  fields.
- **Every field carries provenance and age.** Each field records its
  source and `observed_at`, and a per-field TTL. A field past its TTL is
  presented as stale, with its age, or omitted — never silently refreshed
  in wording while old in fact.
- **Consumers get a bounded, labelled block.** The snapshot renders into
  the prompt as a compact block with ages inline ("calendar, 3 min old:
  dentist at 16:00"), inside a character budget like recall's. Consumers
  may also read the structured snapshot directly.
- **A principal-state section.** The snapshot also describes the user,
  not just the user's surroundings: declared availability windows, a
  coarse attention budget (how many minutes a day the user wants to
  spend on assistant asks), current major commitments with their end
  dates, and an effort-sensitivity preference. Today Sutra budgets its
  own tokens and research and caps offers at four a day, but it has no
  model of the user's time, attention, or energy — so it cannot tell an
  ask that costs the user two minutes from one that costs an evening.
  Principal state is declared by the user or confirmed by them, never
  inferred from behaviour, and it obeys the same provenance and
  staleness rules as every other field.
- **Consumers plan against the principal, not just the world.** The
  ask-first arbiter attaches an estimated user-effort (minutes, and
  whether the ask needs a decision, a review, or hands-on work) to
  every offer, and defers — visibly, never silently drops — offers that
  exceed the user's declared remaining budget. A planner decomposing
  work prefers steps Sutra can complete itself within its granted
  autonomy, and states the expected user-effort of any step that bills
  the user's time. When principal state is absent or stale, consumers
  fall back to today's behaviour (the offer cap alone); nothing blocks
  on missing principal state.
- **Failures are absences, not guesses.** A source that errors or times
  out contributes no field. The snapshot never fills a gap from memory
  and never presents a remembered fact as a live observation.
- **Nothing new is persisted as truth.** The snapshot is a view, cached
  only in memory for its TTL. The underlying stores stay the record.
- Out of scope, deliberately: continuous background polling or push
  updates (assembly is on turn start and on request), precise location
  tracking (presence is a coarse, user-visible hint), copying financial
  figures into the snapshot (pointers only — figures are read through the
  finanxe tools when actually needed), and cross-user state of any kind.
  Inferring the user's capacity from behaviour, or scraping a
  calendar to guess it, is likewise out of scope: principal state is
  declared or confirmed only.

## Capabilities

### New Capabilities
- `world-state`: an on-demand, per-user snapshot of presence, calendar, finance pointers, open commitments, and fresh events, with per-field source, age, and staleness
  Its fields include principal state, and offers and plans are shaped
  by the user's declared capacity.

### Modified Capabilities
(none — consumers adopt the snapshot additively; their existing requirements are unchanged)

## Impact

- Orchestrator: a new `worldstate` package (provider interface, assembly,
  field registry with TTLs, prompt rendering) following the memory and
  offers layout; no new database.
  One deliberate exception to the read-model rule: principal state is
  user-declared data, held in a small per-user store with the same
  protections as the memory stores; the snapshot itself still persists
  nothing.
- The offers arbiter and any planner become consumers of effort
  estimates and the declared budget; their existing behaviour is the
  fallback when principal state is absent or stale.
- Reads, never writes: memory recall, reminders store, offers store,
  episode graph, and — through the gateway — the calendar and finanxe
  snapshot tools. Consumes `inbound-events` for the fresh-events field.
- Depends on `per-user-identity` (a snapshot is always exactly one user's)
  and on `direct-answers` (its volatile-fact rules become consumers of
  the snapshot rather than parallel checks, over time).
- No gateway changes beyond the tool reads that already exist; no twin or
  finanxe changes.
