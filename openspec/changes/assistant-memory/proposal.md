## Why

Sutra's goal is a personal assistant that knows the user and gets better
with use. The text orchestrator (`text-orchestrator`) can answer a
question, but every session starts blank: it does not know the user's
preferences, what was discussed yesterday, or what they corrected last
week. Memory is the foundation for everything after it — learning from
corrections, proactive briefs, a personality that fits the user — and
nothing in that list works without a place to put what the assistant
learns. It is also the riskiest new surface (persistent state that
influences future behaviour), so it is worth building on its own with its
safety rules settled up front.

## What Changes

- Add a local memory store, implemented as a real provider behind the
  `MemoryProvider` interface that `text-orchestrator` defines.
- Store two kinds of record: **episodes** (what happened in a turn) and
  **memories** (durable facts and preferences about the user), each
  carrying its source (stated by the user, inferred, or derived from a
  tool) and provenance.
- Recall relevant memories at the start of each turn and place them in the
  prompt as labelled context.
- Create memories from what the user *says*: an isolated extractor reads
  only the user's own utterance (never tool results) and emits facts and
  preferences they stated or corrected.
- Give the user full control: list, search, edit, and delete memories from
  the REPL. Deleting removes the data, not just hides it.
- Keep the store on the local machine, in a permission-restricted file,
  with no network access of its own.
- Out of scope, deliberately: automatic reflection over past episodes,
  self-edited prompts or skills, and proactive triggers. Those are the
  following changes and depend on this store.

## Capabilities

### New Capabilities
- `assistant-memory`: a persistent, inspectable, user-controlled store of episodes and memories with provenance-aware recall

### Modified Capabilities
(none)

## Impact

- New code under `orchestrator/` (a memory package and REPL commands) plus
  a local SQLite file, gitignored.
- No gateway, twin, or finanxe changes.
- Depends on `text-orchestrator` (the `MemoryProvider` seam and the
  classifier pattern it establishes).
- Sensitive data lands on disk: preferences, conversation text, and
  whatever personal facts the user states. Financial figures reach disk
  only through reply text recorded in episodes (see design).
- One new model call per turn (the extractor), with a small model.
