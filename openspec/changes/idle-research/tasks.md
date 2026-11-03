## 1. Storage and switch

- [x] 1.1 `idle/db.py`, `store.py`: owner-only versioned SQLite for runs (topic, brief, kind, outcome, findings capped, signal id, time, revisit-not-before) and meta (on/off switch, failure streak)
- [x] 1.2 Tests: persistence, file mode, switch precedence over the environment default, forget

## 2. Picker and brief checks

- [x] 2.1 Prompt `idle_picker.md`, a forced-schema `idle_pick` call, and input assembly from approved interests, recent plan topics (no gists), dates, prior runs, per-topic reactions
- [x] 2.2 Validation: number, revisit clamp, blocked topics and muted interests skipped, value against the research bar
- [x] 2.3 Brief checks in code (length, email, phone, long digit runs, currency, URLs, blocked words)
- [x] 2.4 Tests: time-sensitive interest picked; none and below-bar run nothing; invalid number is none; revisit period respected; private brief rejected

## 3. Run, summarise, deliver

- [x] 3.1 Eligibility: switch, dependencies, quiet time (orchestrator last-activity), no pending or running job, daily cap, minimum gap, reserve for the user, failure backoff
- [x] 3.2 Run through `AgentService.run` tagged `idle:`; cancellation recorded as interrupted
- [x] 3.3 Summariser (tools off, untrusted block, three sentences, "As of" date, URLs stripped) and signal filing (kind `research`, three-day expiry)
- [x] 3.4 Offers: a `research` signal is always an ask; accepted detail given in the untrusted block; research bar updated from the outcome
- [x] 3.5 Tests: each eligibility rail; failure doubles the gap; injection in findings does not act; teaser carries no detail; expired finding never spoken; bar moves with outcomes

## 4. Control, wiring, docs, verification

- [x] 4.1 `/idle` commands; `SUTRA_IDLE_RESEARCH`, `_DAILY_RUNS`, `_MIN_HOURS`, `SUTRA_IDLE_DIR`; text and voice wiring; periodic task and clean shutdown
- [x] 4.2 README section
- [x] 4.3 Manual check with a real key: add an interest, `/idle now`, read the run in `/agents` and `/idle show`, then take the offer in text and judge the teaser and summary
