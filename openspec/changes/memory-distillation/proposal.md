## Why

`assistant-memory` remembers what the user *said*, one utterance at a
time, through an extractor that deliberately sees nothing else. That
isolation is a safety property, and it leaves a gap: much of what an
assistant should know is never stated in one sentence. It accumulates
across episodes — a preference shown three times, a fact spread over two
conversations, and above all **open commitments**: "I owe Brandon the
proofs by Dec 4", "the check arrives this week, then the rollover clock
starts". Those live scattered across episode records, owned by nobody,
and nothing ever gathers them up. The episode graph links topics, and
`self-learning` distils lessons about the assistant's *behaviour*, but
the user's life facts have no distillation step, and contradiction
handling today is only the write-time, same-kind text-overlap check in
the extractor's path.

This change adds the missing pass: a scheduled, deliberate compression
of recent episodes into durable semantic form — facts, preferences, and
commitments — that the user reviews and can correct, with provenance
back to the episodes each claim came from.

## What Changes

- **A scheduled distillation pass.** On a schedule (and on demand), a
  small-model pass reads hot episodes since the last pass's watermark
  and emits candidate memories: `fact` and `preference` as today, plus a
  new kind, **`commitment`** — something the user owes, is owed, or is
  waiting on, with its horizon (a date or event) when the episodes state
  one.
- **Everything arrives as a proposal.** Candidates are stored `proposed`
  with source `inferred` and flagged as distilled, entering the existing
  `/proposals` review flow unchanged: nothing is recalled or treated as
  fact until the user approves it. Tool results are not read by the
  pass — it reads episode records (user utterances and tool *names*),
  never raw tool payloads, which memory does not store anyway.
- **Provenance is plural.** A distilled memory links to every episode
  that supports it, so `/why` can show the pattern, not just one
  utterance. A candidate supported by a single weak mention is marked as
  such in the review listing.
- **Contradictions supersede, never stack.** When an approved distilled
  memory contradicts an active memory, the older one becomes
  `superseded` (visible, not deleted), reusing the memory store's
  existing mechanism — including when the contradiction is with a
  `user_stated` memory. Approval is the moment of supersession, so the
  user sees the replacement as one decision: "replace X with Y?"
- **The user is told, in digest form.** One notice per pass that changed
  something: how many proposals await review, and the commitments among
  them called out, since those are the time-sensitive ones. No per-item
  notice spam.
- **The pass is bounded and resumable.** A persisted watermark (last
  episode distilled), a daily model-call cap in the style of
  `idle-research`, and idempotent re-runs: a crashed pass re-reads from
  the watermark and does not duplicate proposals.
- Out of scope, deliberately: auto-approving any category (a later
  policy decision, once approval data shows which categories the user
  always accepts), reading the cold episode archive (hot episodes only;
  archive opt-in was already left open in `assistant-memory`), distilling
  lessons about the assistant's behaviour (that is `self-learning`), and
  acting on commitments — a commitment memory is surfaced by recall and
  can feed reminders or offers through their existing paths, but this
  change creates neither.

## Capabilities

### New Capabilities
- `memory-distillation`: a scheduled episodic-to-semantic pass that proposes facts, preferences, and commitments with multi-episode provenance, superseding contradicted memories on approval

### Modified Capabilities
(none — the memory store's proposal, approval, and supersession mechanics are reused as they are; `commitment` is a new memory kind within the existing schema's kind field)

## Impact

- Orchestrator: a new `distill` package (pass runner, watermark,
  candidate schema, digest notice) beside the memory package; a schema
  note that `commitment` memories may carry a horizon field; REPL adds
  `/distill` (run now, show last pass) alongside the existing
  `/proposals` flow.
- Depends on `assistant-memory` (episodes, proposals, supersession) and
  composes with `episode-graph-offers` (graph open items are a useful
  input signal, not a requirement). Independent of the identity and
  events changes; runs per user against that user's memory database.
- Cost: one small-model pass per schedule window over recent episodes,
  capped daily. No gateway, twin, or finanxe changes.
