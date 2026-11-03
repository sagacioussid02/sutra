## 1. Profile and rules

- [x] 1.1 `personality/db.py`, `store.py`: owner-only versioned SQLite for styles (score, tries, reactions) and meta (level, variety, on/off, judged window)
- [x] 1.2 Eligibility rules (heavy topics, upset, gap) and softmax style choice, with an injectable random source
- [x] 1.3 Tests: defaults, each exclusion, gap, level zero, variety

## 2. Orchestrator and learning

- [x] 2.1 Humor note on the first model step only; none after a tool call or on the read-back
- [x] 2.2 `humor_reaction` structured call; background check on the next turn; score and level updates; stop handling
- [x] 2.3 `adjust_humor` tool; `/humor` commands; `SUTRA_HUMOR`; text and voice wiring
- [x] 2.4 Tests: note placement, tools suppress it, reactions move scores, level drift, stop, failure changes nothing, no added waiting

## 3. Docs and check

- [x] 3.1 Persona line, README
- [x] 3.2 Live check with a real key: offer humor on a plain chat turn and read the reaction call
