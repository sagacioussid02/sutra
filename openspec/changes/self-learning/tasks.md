## 1. Storage and model

- [x] 1.1 `lessons/db.py`, `store.py`: owner-only versioned SQLite for lessons, evidence, history, meta; statuses and effects as in the spec
- [x] 1.2 Schema validation of model output (effect and kind enums, lengths, no free-form fields); text tripwire for safety words
- [x] 1.3 Tests: persistence, file mode, out-of-schema discarded, tripwire, forget removes evidence

## 2. Proposing

- [x] 2.1 `SqliteMemory.recent_exchanges`; pairing of previous reply and next utterance, exclusions, truncation
- [x] 2.2 Prompt `lessons.md`, forced-schema `reflect_lessons` call, validation (pair numbers, caps, similarity to every earlier lesson, rejected never again)
- [x] 2.3 Deterministic outcome pass over `offers.db` for block lessons
- [x] 2.4 Tests: repeated correction proposed; nothing clear yields none; rejected stays rejected; finance excluded; mixed outcomes yield no block lesson; caps

## 3. Approval and effects

- [x] 3.1 Offers: add a ready signal with code-built wording that skips the judge; a resolve hook by source; the orchestrator acknowledges an accepted lesson
- [x] 3.2 Lesson service: approve, reject, defer, retire; `block` applied through offers controls; `retire_lesson` tool
- [x] 3.3 Prompt block: only active guidance, newest first, capped, labelled
- [x] 3.4 Tests: yes, no, not now; the model cannot approve; only active lessons reach the prompt; the confirmation gate behaves identically with lessons present

## 4. The gate

- [x] 4.1 `lessons/probes.jsonl` and `evals/run_lesson_probes.py`: baseline and with-lesson runs, relative comparison
- [x] 4.2 Activation: pass activates, regression blocks with reason, inability to run leaves it approved; `/lessons recheck`
- [x] 4.3 Tests with a scripted model: harmless passes, violating lesson blocked, no key leaves it waiting; the probe file is well-formed

## 5. Recurrence, control, docs

- [x] 5.1 Recurrence detection and revision proposals; "not working" shown in `/lessons`
- [x] 5.2 `/lessons` commands; `SUTRA_LESSONS`, `SUTRA_LESSONS_REFLECTION`, `SUTRA_LESSONS_DIR`; text and voice wiring; daily maintenance task
- [x] 5.3 README section
- [ ] 5.4 Manual check with a real key: feed a repeated correction, take the proposal, approve it, watch the probe run, then see the lesson change an answer and run `/lessons retire`
