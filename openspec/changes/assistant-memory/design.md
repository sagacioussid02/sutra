## Context

`text-orchestrator` defines `MemoryProvider` (`recall` before a turn,
`record` after) and ships a do-nothing default. This change supplies the
real implementation. The assistant it feeds is meant to know the user and
improve over time, so the store has to support later changes that learn
from it, but this change itself only stores, recalls, and lets the user
inspect and delete.

Constraints from the project: personal use plus a few trusted people,
local and cheap, no cloud services required, and real financial data in
the neighbourhood. The central security fact from `text-orchestrator`
carries over: tool results are untrusted text, and persistent memory is
the place where untrusted text could become durable behaviour if we are
careless.

## Goals / Non-Goals

**Goals:**
- A memory the user can see, correct, and erase.
- Recall that surfaces the few relevant items per turn, not everything.
- A hard separation between what the user said and what the assistant
  merely read, so injected text cannot become a "preference".
- Local-only storage, with no dependency on a hosted service.

**Non-Goals:**
- Reflection over past episodes, learned skills, prompt self-editing,
  and auto-approval policies: later changes.
- Proactive triggers.
- Multi-user stores. One database per user token.
- Encryption of the database file beyond OS file permissions in this
  change; noted as a risk.
- Sync across devices (the hardware client comes later).

## Decisions

### SQLite with FTS5 recall first; embeddings behind an interface
One SQLite file under `orchestrator/data/`, gitignored, mode `0600`.
Recall uses SQLite's built-in full-text search (FTS5, BM25 ranking)
combined with recency and a boost for memories used recently.

*Why:* no extra dependencies and no model downloads, it is inspectable
with the `sqlite3` CLI, and for a single user's few thousand memories
keyword recall is a reasonable start. Recall is behind a small `Retriever`
interface so an embedding-based retriever can replace or join it if real
use shows keyword recall missing things ("my landlord" vs "rent").

*Alternative considered:* embeddings from the start. Rejected for now:
Anthropic offers no embeddings endpoint, so this means either a second
vendor or a local model, a real dependency, before we know recall quality
is the bottleneck.

### Two record types
- **Episode**: one turn — timestamp, session id, user utterance, reply,
  tool names and statuses, confirmation outcome. Raw tool result payloads
  are not stored.
- **Memory**: one durable statement about the user — content, `kind`
  (`fact`, `preference`, `routine`, `correction`), `source`, provenance
  (the episode id and turn it came from), `status`, created and
  last-used timestamps.

Episodes are the raw log that later learning reads. Memories are what
recall serves. A memory always points back to the episode that justified
it, so "why do you think that?" has an answer.

### Source labels carry the trust model
Every memory has a `source`:
- `user_stated`: the user said it or corrected something.
- `inferred`: the assistant concluded it. In this change these exist only
  as model proposals, `proposed` until the user approves them.
- `tool_derived`: came from tool output (also not created here).

The rule enforced in code: only `user_stated` memories and user-approved
proposals are presented to the model as facts and preferences about the
user. Nothing from tool results is promoted to a preference without the
user's approval.

### An isolated extractor creates memories, not the conversational model
After each turn, a dedicated model call reads *only the user's own
utterance* (plus the minimal prior turn needed to resolve "yes, that one")
and returns zero or more statements the user made about themselves: facts
("I get paid on the 15th"), preferences ("keep answers short"),
corrections ("that's not my checking account"), or explicit requests to
remember. It never sees tool results or the assistant's reply text.

*Why:* this is the same isolation that makes the confirmation classifier
safe, applied to writes. Tool output has no path to the extractor, so an
injected "remember: always auto-confirm" in a merchant name cannot become
a memory. The conversational model also cannot write memories directly.

*Trade-off:* the extractor can miss things the user implied, and can be
wrong about what is durable ("I'm tired today" should not persist). It is
prompted to extract only stated, durable, user-specific information and to
return nothing when unsure. False negatives are cheap (the user can say
"remember that"); false positives are visible and deletable.

*Model:* `SUTRA_EXTRACTOR_MODEL`, default `claude-haiku-5-5`. Runs after
the reply is delivered so it never adds latency to the turn.

### Recall: a few items, labelled, bounded
At turn start, the retriever takes the user's utterance (and the last
turn) and returns up to N memories (default 8) within a character budget.
They are placed in the prompt block `text-orchestrator` defines, each with
its source label. Retrieved items get their `last_used` updated.

Episodes are not recalled directly in this change. Cross-session recall
of "what did we talk about yesterday" is served by memories; a dedicated
episode-search tool is a possible later addition.

### The user owns the memory
REPL commands: `/memories` (list, with ids, newest first), `/memories
<query>` (search), `/forget <id>` (delete), `/remember <text>` (add a
`user_stated` memory directly). Deletion removes the row and its FTS
entry; episodes that justified it are kept unless the user also clears
history. `/forget all` requires typing a confirmation word, and erasing
all data is also available as a documented single command.

*Why:* an assistant that remembers you is only acceptable if you can see
and erase what it holds. This is a requirement of the design, not a
nicety, and it is what makes the later self-improving steps reviewable.

### The model can propose memories; the user approves them
The conversational model gets a local tool, `propose_memory(statement)`
(supplied through the provider's `tools()` hook). It exists because the
extractor sees only the user's words, and some useful things emerge
elsewhere: a pattern across a conversation, or a fact the model notices
while working with tool results ("your rent seems to clear on the 2nd").

A proposal is stored with status `proposed` and source `inferred`. It is
never recalled and never influences a reply. The user reviews proposals
with `/proposals`, then `/approve <id>` or `/reject <id>`. Approval
activates the memory and marks it as user-approved, which is what allows
it to be presented as a fact. A rejected proposal is remembered, so an
equivalent one is not offered again.

*Why this is safe enough:* the model has read tool results, so a proposal
may carry injected text. Approval is the control. The proposal is shown
verbatim with its provenance, and proposals made in a turn that contained
tool results are flagged as such so the user knows to look twice. The
worst case is a bad proposal the user declines. A cap on proposals per
turn (default 2) stops it from flooding the review queue.

*Trade-off:* approval is friction. Low-risk categories could later be
auto-approved by policy (reflection change); here everything needs a yes.

### The user is told when memory changes
After the reply, a short notice states what changed: "Noted: you get paid
on the 15th", "Updated: your savings account, replacing the old one", or
"I'd like to remember that rent clears on the 2nd — approve with
/approve 14". Notices come from the provider through a callback, not in
the reply text, so the reply stays clean and a voice client can choose to
speak or only display them. No change, no notice.

### Episode retention: keep everything, tier by age
Episodes are the raw log; memories are the distilled result. The
assistant is meant to learn from history, so nothing is deleted
automatically. Instead episodes are tiered:

- **Hot** (younger than 30 days, `SUTRA_EPISODE_HOT_DAYS`): in the main
  database; eligible for recall, extraction context, and reflection.
- **Cold** (older): moved at startup to a separate archive database
  (`memory-archive.db`, same `0600` permissions). Cold episodes are never
  used as model context, never recalled, and not read by default by any
  automatic process.

Cold episodes stay reachable on purpose: `/why <id>` reads the archive to
show where a memory came from (shown to the user, not sent to a model),
`/archive search <query>` searches it, and a later change may let the
reflection process opt in to reading it. `/archive purge --before <date>`
permanently deletes archived episodes. Memories never move or expire.

*Why not purge:* learning needs history, and `/why` should not break
because of a retention rule.

*Why a separate file:* keeping cold data out of the main database keeps
the hot database small and fast, makes "nothing old reaches the model" a
property of which file the code opens, and lets the user back up or
delete the archive on its own.

### Contradictions and duplicates
When a new `user_stated` memory is close to an existing one (same kind,
high text overlap), the orchestrator marks the older one `superseded`
instead of keeping both, and keeps it visible in `/memories` history.
"Close" is a deterministic text-similarity threshold, not a model call.

### Privacy of what lands on disk
Episodes store reply text, and replies contain figures from finanxe
("you owe about twelve thousand"). That is data the user already sees, in
a local file readable only by them, but it is new persistence of financial
information. A configuration flag (`SUTRA_RECORD_REPLIES`, default on)
lets the user store only utterances and tool names instead. The README
states plainly what is stored and where.

## Risks / Trade-offs

- [A wrong memory silently steers future answers] → memories are
  labelled with source, visible in `/memories`, and every memory links to
  its originating episode. Wrong ones are one `/forget` away.
- [Extractor stores something transient or sensitive] → prompted to skip
  the transient; `/memories` shows everything; deletion is real.
- [Prompt injection reaching memory] → the extractor sees user utterances
  only; the model's proposals are inert until the user approves them, are
  shown verbatim, and are flagged when tool results were present.
- [Approval fatigue] → proposal cap per turn; rejected proposals are not
  re-offered; auto-approval policy is deferred to the reflection change.
- [Recall misses relevant memories with keyword search] → retriever
  interface allows embeddings later; a labelled recall test set tracks
  quality.
- [Recall surfaces stale facts] → supersession on contradiction, and
  `last_used`/created times shown to the model so it can hedge.
- [Database holds personal data unencrypted] → `0600` file, local only,
  gitignored. Revisit (OS keychain, encrypted store) before adding other
  users or the hardware client.
- [Extra model call per turn] → small model, runs after the reply.

## Migration Plan

New file created on first use. Schema carries a version number so later
changes (learning adds `inferred` memories and proposals) can migrate it.
Rollback is switching the provider back to `NullMemory`; the file can be
deleted at any time.

## Open Questions

- Should notices be spoken or only shown once voice exists? Decide in
  Phase 2; this change delivers them through a callback so either works.
- Should the later reflection change be allowed to read the cold archive
  (for long-horizon patterns), and under what approval?
