## 1. Facts, questions, judge

- [x] 1.1 `auth/` store (facts, burned, meta), filters, retention, channel
- [x] 1.2 Question writer (prompt, schema) with grounding checks, kind rotation
- [x] 1.3 Judge (exact match, schema, fail closed); labelled set and eval runner
- [x] 1.4 Tests

## 2. Challenges and gating

- [x] 2.1 `AuthService`: levels, retries, failure, cooldown, grant, cancel, timeout, distress answer, too-little-data
- [x] 2.2 Safety: an authenticated way to raise the mode
- [x] 2.3 Orchestrator: challenge handling, protected-tool gate, voice mode return, channel on each turn
- [x] 2.4 Flipper: setting, saved value, `/auth`, key, keyboard-only off
- [x] 2.5 Tests, README, live checks
