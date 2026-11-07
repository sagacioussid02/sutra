## Context

The memory design drew a careful line: the extractor sees only the
user's own utterance, so nothing the assistant read can become a
"preference" unnoticed; the conversational model may propose memories,
which stay inert until approved. Both mechanisms are per-turn. What
neither does is look *across* turns: patterns, slow changes, and
commitments stated in pieces.

Episodes already hold the raw material (utterance, tool names and
statuses, confirmation outcomes — never raw payloads), tiered hot/cold
with a 30-day hot window. The graph holds what was discussed and left
open. This change is the periodic reader of that material, designed so
its extra reach does not weaken the line: its output is proposals, and
approval — with the full provenance in front of the user — is what
makes any of it true.

## Goals / Non-Goals

**Goals:**
- Durable facts, preferences, and open commitments gathered from across
  episodes, not just single utterances.
- Every distilled memory traceable to the episodes that support it.
- Contradictions resolved by supersession at approval time, never by
  quietly keeping both or silently deleting either.
- A pass the user can run, pause, inspect, and afford: scheduled, capped,
  and resumable.

**Non-Goals:**
- Auto-approval. Everything distilled is a proposal in this change.
- Reading the cold archive. Hot episodes only; long-horizon patterns
  over archived material wait for the archive opt-in decision already
  open in `assistant-memory`.
- Behaviour lessons. `self-learning` owns how the assistant should act;
  this owns what is true about the user's life.
- Acting on commitments (creating reminders, sending anything). A
  commitment is a memory kind; other features may consume it later.

## Decisions

### A batch pass with a watermark, not a per-turn process
The pass runs on a schedule (default daily, in an idle window, in the
style of `idle-research`) over episodes with ids above the stored
watermark, in bounded batches. On completion the watermark advances to
the last episode actually processed. A manual `/distill` runs the same
code path now.

*Why:* cross-episode patterns need a window per-turn processing cannot
see, and batch keeps the model cost predictable and capped. The
watermark makes crashes and caps safe: unprocessed episodes are simply
next pass's input.

*Alternative considered:* distil at episode closing, incrementally.
Rejected: an episode that just closed has no distance from itself; the
patterns worth catching (third mention, a change from last month) need
the batch view, and per-close calls cost more for less signal.

### Candidates are proposals with plural provenance
The pass emits candidates in a forced schema: statement, kind
(`fact` / `preference` / `commitment`), horizon for commitments (date or
event phrase, as stated — never a date the model invents), the
supporting episode ids, and a support count. Storage reuses the memory
store: status `proposed`, source `inferred`, plus a `distilled` flag
and the episode-id list in provenance. Single-episode support is shown
in review as thin support, not hidden.

*Why:* this keeps one review queue, one approval mechanic, and one
recall rule — only `user_stated` and user-approved memories are facts —
instead of a second, weaker truth channel for distilled content.

### Supersession is proposed, then decided at approval
The pass may mark a candidate as *replacing* a specific active memory
when they conflict (same subject, incompatible claim). The review shows
the pair. Approving performs the store's existing supersession: old
becomes `superseded`, kept and listed; rejecting leaves both alone.
This applies even when the older memory is `user_stated` — the user's
approval of the replacement is itself a user decision, which is what
makes superseding a stated memory legitimate. Without the pair marking,
a merely additional candidate never supersedes anything.

### Commitments are memories, with a horizon
A commitment memory's content is the obligation in plain words ("owes
Brandon the $0-balance proofs"), and its horizon is stored as stated
("by Dec 4", "when the check arrives"). The pass does not resolve
relative phrases to dates and does not invent horizons; a commitment
without a stated horizon is stored without one. Recall treats
commitments like other memories; their time-sensitivity is a display
concern (digest call-out, listing order), not a new mechanism.

### Input discipline
The pass reads episode records only: user utterances, tool names and
statuses, confirmation outcomes. It never sees tool payloads (memory
does not store them) and never sees reply text when reply recording is
off — in that configuration it works from utterances alone, and the
design accepts the thinner signal rather than weakening the recording
choice.

## Risks / Trade-offs

- [A distilled "fact" is a plausible hallucination] → proposals only,
  plural provenance shown at review, thin support flagged, and `/why`
  reaches every supporting episode.
- [Approval fatigue returns] → one digest notice per pass, commitments
  called out first, and approval statistics are the evidence a later
  auto-approval policy would need — gathered, not assumed.
- [The pass re-proposes what was rejected] → rejected proposals are
  recorded by the store; the pass's input includes prior rejections for
  the same episodes and its prompt forbids re-emitting equivalents.
- [Cost creep as episodes accumulate] → watermark plus batch bound plus
  a daily call cap; a backlog drains over several passes rather than one
  large one.
- [A commitment's horizon goes stale silently] → horizons are stored as
  stated and shown with their age through normal memory surfaces; a
  commitment the user completes can be forgotten or superseded like any
  memory. (Watching commitments against the world is `world-state`'s
  job, later.)

## Migration Plan

Additive: a watermark table in the memory database (schema version
bump, refused-by-older-code rules unchanged), the `distill` package, and
the schedule. First run starts from the current end of the episode log
unless the user asks for a backfill window, so enabling it does not
produce a flood of proposals about old conversations. Turning the
schedule off leaves stored proposals reviewable and nothing else
running.

## Open Questions

- Backfill: should the user be offered a one-time pass over the existing
  hot episodes at enablement? Leaning yes, explicitly opt-in, because
  the current log is where the first commitments already live.
- Should an approved commitment automatically be *offered* as a reminder
  through the existing ask-first path? Attractive, and deliberately left
  to a follow-up so this change stays about memory.
