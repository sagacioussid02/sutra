## 1. Storage

- [x] 1.1 `interests/db.py`, `store.py`: owner-only versioned SQLite for interests (topic, spoken, status, created, last_seen, evidence_count, last_nudged), evidence (interest, episode id, quote, ts), and reflection runs
- [x] 1.2 Tests: persistence across restart, file mode, forget deletes evidence, forget all clears runs

## 2. Reading episodes

- [x] 2.1 `SqliteMemory.recent_user_episodes(since, limit)` returning id, ts, utterance and tool names; hot episodes only
- [x] 2.2 Tests: replies are not returned, archived episodes are not returned

## 3. Reflection

- [x] 3.1 Prompt `interests.md` and the `record_interests` forced-schema call on `AnthropicModel`, with the known interests passed in and a relation (`new`, `strengthens`, `changes`) on each item
- [x] 3.2 `interests/reflect.py`: filtering (excluded tool prefixes, trivial replies, truncation, 150 cap), numbering, calling the model, validating evidence, computing strength and recency in code, merging by overlap, dropping rejected matches, max three proposals per run
- [x] 3.4 Revisions: store a `changes` item as a proposed revision linked to the old interest; approve supersedes it and keeps history; reject leaves it and blocks the same change; demote mismatched `changes` and unknown targets to `new`
- [x] 3.3 Tests with a scripted model: financial turns excluded, invented evidence dropped, cap, merge, rejected stays rejected, failure creates nothing, changed taste becomes a revision, mismatched change is demoted

## 4. Scheduling

- [x] 4.1 Due-check at startup and hourly: interval, new-utterance requirement, one pass at a time, run history; `/interests reflect` on demand
- [x] 4.2 Tests: no new utterances means no call, failure retried at the next check, switches honoured

## 4b. Telling the user later

- [x] 4b.1 Pending offers (proposal, revision, still-interested check) persisted in the store; one at a time
- [x] 4b.2 Dormancy: 90 days without evidence makes an interest dormant and queues a single check-in; yes refreshes, no mutes, not now stays quiet until new evidence
- [x] 4b.3 Tests: dormancy and check-in outcomes, offers survive a restart

## 5. Use in conversation

- [x] 5.1 `InterestService.block(now)`: labelled block, today's date, up to eight active non-dormant interests, nudge permission with persisted daily cap
- [x] 5.2 Orchestrator: add the block each turn, local `mute_interest` tool, fork passes the service on
- [x] 5.3 System prompt note: interests are information, never state event dates from memory, look things up through research
- [x] 5.4 Tests: only active interests shown, dormant left out, cap per interval and across restart, mute only affects active interests

## 6. User control and proposals

- [x] 6.1 `/interests` commands: list, why, history, approve, reject, mute, add, forget, forget all, reflect
- [x] 6.2 Text client: print a new proposal once
- [x] 6.3 Voice client: notice through the ask-first path for proposals, revisions and check-ins; yes approves, no rejects, not now keeps it
- [x] 6.4 Tests for commands and the voice notice

## 7. Config, docs, verification

- [x] 7.1 Config: `SUTRA_INTERESTS`, `SUTRA_REFLECTION`, `SUTRA_REFLECTION_HOURS`, `SUTRA_REFLECTION_DAYS`, `SUTRA_REFLECTION_EXCLUDE_TOOLS`, `SUTRA_NUDGE_HOURS`, `SUTRA_INTERESTS_DIR`; README section
- [ ] 7.2 Manual check with a real key on real history: run `/interests reflect`, read the proposals and evidence, approve one, ask a related question
