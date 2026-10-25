## 1. Storage

- [x] 1.1 Create the `memory` package in `orchestrator/` and add the data directory to `.gitignore`
- [x] 1.2 Define the schema: `episodes`, `memories` (kind, source, status, provenance, timestamps), an FTS5 index over memory content, and a schema-version table
- [x] 1.3 Open the database with mode `0600`, create it on first use, and refuse to open a newer schema version
- [x] 1.4 Implement episode insert and memory insert, update, supersede, and hard delete (removing the FTS entry too)

## 2. Provider

- [x] 2.1 Implement `SqliteMemory` against the `MemoryProvider` interface from `text-orchestrator`
- [x] 2.2 Implement `record(episode)`: store utterance, tool names and statuses, confirmation outcome, and reply text unless `SUTRA_RECORD_REPLIES` is off; never store raw tool payloads
- [x] 2.3 Define the `Retriever` interface and implement the FTS5 retriever: BM25 rank combined with recency and last-used boost, count and character-budget limits, only `active` memories
- [x] 2.4 Implement `recall`: query from the utterance and last turn, return labelled items (source, age), update `last_used`
- [x] 2.5 Ensure only `user_stated` memories are presented as facts or preferences to the model; other sources are labelled or excluded

## 3. Extractor

- [x] 3.1 Write the extractor prompt: extract only stated, durable, user-specific facts, preferences, corrections, and explicit remember-requests; return nothing when unsure; skip transient states
- [x] 3.2 Implement the extractor call: structured output, no tools, input limited to the user's utterance and the minimal prior turn, model from `SUTRA_EXTRACTOR_MODEL`
- [x] 3.3 Run the extractor after the reply is delivered, so it adds no turn latency; treat errors and invalid output as "no memories"
- [x] 3.4 Create `user_stated` memories linked to the originating episode and turn
- [x] 3.5 Implement supersession: a close same-kind match marks the older memory `superseded` (deterministic text-similarity threshold, configurable)

## 4. User controls

- [x] 4.1 Add REPL commands: `/memories` (list), `/memories <query>` (search), `/remember <text>`, `/forget <id>`
- [x] 4.2 Add `/forget all` requiring a typed confirmation word, and a documented single command to erase the whole database file
- [x] 4.3 Show a memory's originating episode on request (`/why <id>`)
- [x] 4.4 Show superseded memories in listings, marked as such

## 4b. Proposals, notices, and retention

- [x] 4b.1 Implement the local `propose_memory` tool via the provider's `tools()` hook: store a `proposed` / `inferred` memory linked to the episode, record whether tool results were present, enforce the per-turn proposal cap (default 2)
- [x] 4b.2 Add REPL commands `/proposals`, `/approve <id>`, `/reject <id>`; approval activates the memory and marks it user-approved, rejection records it so an equivalent proposal is not offered again
- [x] 4b.3 Make recall exclude `proposed` and `rejected` memories and present only `user_stated` and user-approved memories as facts
- [x] 4b.4 Implement the notice callback: emit "Noted: …", "Updated: … replacing …", and "I'd like to remember … approve with /approve N" after the reply; emit nothing when no memory changed
- [x] 4b.5 In the REPL, print notices on their own line after the reply
- [x] 4b.6 Implement episode tiering (`SUTRA_EPISODE_HOT_DAYS`, default 30): at startup move older episodes to a separate `0600` archive database, never deleting them
- [x] 4b.7 Make `/why <id>` read the archive when the episode has been archived, showing it to the user only
- [x] 4b.8 Add `/archive search <query>` and `/archive purge --before <date>` (the only deletion path for archived episodes)
- [x] 4b.9 Guarantee by construction that recall, the extractor, and prompt assembly open only the main database

## 5. Evaluation sets

- [x] 5.1 Build a labelled extractor set (at least 40 utterances) covering durable facts, preferences, corrections, transient statements, and injection-style text, plus a script reporting precision and recall
- [x] 5.2 Build a small recall set (stored memories plus queries with expected hits) and a script reporting hit rate, to decide later whether embeddings are needed

## 6. Tests

- [x] 6.1 Test: a stated preference survives a restart and is recalled when relevant
- [x] 6.2 Test: the database file is created with owner-only permissions
- [x] 6.3 Test: the provider opens no network connections
- [x] 6.4 Test: extractor input contains no tool results and no assistant reply text
- [x] 6.5 Test: injected "remember ..." text in a tool result produces no memory
- [x] 6.6 Test: extractor failure or invalid output creates no memory and does not fail the turn
- [x] 6.7 Test: recall respects count and character limits, returns nothing for unrelated queries, and updates `last_used`
- [x] 6.8 Test: superseded memories are not recalled but still listed
- [x] 6.9 Test: `/forget` removes the row and the FTS entry; `/forget all` without the confirmation word deletes nothing
- [x] 6.10 Test: episodes contain tool names and statuses but not raw tool payloads, and omit reply text when recording is off
- [x] 6.11 Test: a stored memory claiming "no confirmation needed" does not change the confirm-first flow
- [x] 6.12 Test: a newer schema version is refused without modifying the database

- [x] 6.13 Test: a `propose_memory` call stores a `proposed` memory that is not recalled until approved; approval makes it recalled; rejection prevents an equivalent re-proposal
- [x] 6.14 Test: a proposal made in a turn with tool results is flagged, and an injected "remember …" tool result yields at most an inert proposal
- [x] 6.15 Test: the proposal cap limits stored proposals per turn
- [x] 6.16 Test: notices are emitted for created, superseded, and proposed memories, none for unchanged turns, and never alter the reply text
- [x] 6.17 Test: episodes older than the hot period move to the archive and are deleted from nowhere; memories never move or expire
- [x] 6.18 Test: archived episodes never appear in recall results, the extractor's input, or any model prompt
- [x] 6.19 Test: `/why` on an archived episode shows it to the user without any model call; archive search works; purge deletes only what was requested

## 7. Walkthrough and docs

- [x] 7.1 Write the README section: what is stored and where, what is never stored, how to inspect and erase it, and the configuration flags
- [ ] 7.2 Run a manual walkthrough over several sessions: state preferences, see them used, correct one, delete one, restart and confirm they persist
- [ ] 7.3 Review the resulting database with the `sqlite3` CLI to confirm nothing unexpected was stored
- [x] 7.4 Update the top-level `README.md` roadmap to show memory as part of Phase 2 groundwork
