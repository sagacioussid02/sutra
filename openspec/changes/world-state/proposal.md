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
- **Every field carries provenance and age.** Each field records its
  source and `observed_at`, and a per-field TTL. A field past its TTL is
  presented as stale, with its age, or omitted — never silently refreshed
  in wording while old in fact.
- **Consumers get a bounded, labelled block.** The snapshot renders into
  the prompt as a compact block with ages inline ("calendar, 3 min old:
  dentist at 16:00"), inside a character budget like recall's. Consumers
  may also read the structured snapshot directly.
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

## Capabilities

### New Capabilities
- `world-state`: an on-demand, per-user snapshot of presence, calendar, finance pointers, open commitments, and fresh events, with per-field source, age, and staleness

### Modified Capabilities
(none — consumers adopt the snapshot additively; their existing requirements are unchanged)

## Impact

- Orchestrator: a new `worldstate` package (provider interface, assembly,
  field registry with TTLs, prompt rendering) following the memory and
  offers layout; no new database.
- Reads, never writes: memory recall, reminders store, offers store,
  episode graph, and — through the gateway — the calendar and finanxe
  snapshot tools. Consumes `inbound-events` for the fresh-events field.
- Depends on `per-user-identity` (a snapshot is always exactly one user's)
  and on `direct-answers` (its volatile-fact rules become consumers of
  the snapshot rather than parallel checks, over time).
- No gateway changes beyond the tool reads that already exist; no twin or
  finanxe changes.
