## Why

A friend remembers that Sam is your brother, that you have the dentist tomorrow, and asks how it went. Sutra remembers topics, not people and plans, and never asks about your life. It also has nothing to say when you just want to talk about a rough day: it answers like a help desk.

## What Changes

- **People and plans.** When a conversation ends, a small call reads only what the user said and keeps two short lists: people they mention (a name and how they are related) and upcoming things (a short description and, when clear, a date). Heavy topics (health, money, loss, legal trouble, crisis) are never kept.
- **They are used naturally.** A short block of known people and upcoming plans goes into the prompt as background, with people mentioned right now first, so "Sam" needs no explanation. Their names also go to the speech recognizer as vocabulary hints.
- **"How did it go?"** The day after a plan, Sutra may ask about it. It is asked directly as a question, at a quiet moment or after an answer, one at a time. How the user reacts teaches a bar: people who engage get more of them; people who ignore or decline get fewer.
- **A rare "how have you been?"** After a stretch of not talking, a greeting from the user can be answered with a short wellbeing question. How often is learned from the same bar.
- **A listening mode.** When the user says they want to talk or sounds down, Sutra stops problem-solving: it reflects, asks one gentle question at a time, offers no lists, does not joke, and adds no unprompted offers. That conversation is not added to the graph. If the user talks about hurting themselves, Sutra responds with care and points to a crisis line and emergency services.
- **Control.** `/life` lists people and plans, adds, forgets one or everything. `SUTRA_LIFE=off` removes it.

Out of scope: tracking anyone's whereabouts, anything about health or money, acting on plans (no booking, no messaging), and long-term emotional profiling.

## Capabilities

### New Capabilities
- `life-followups`: people and plans, natural use of them, bar-paced check-ins, and a listening mode.

### Modified Capabilities
(none)

## Impact

- New package `orchestrator/src/sutra_orchestrator/life/` and a local `life.db` (owner-only).
- `GraphService` gains an episode-close hook and skips private turns. `OffersService` treats a check-in as an open question (answered by any engaged reply). `Orchestrator` adds the people block, the listening note, and private-turn handling.
- One small extraction call per kept episode.
