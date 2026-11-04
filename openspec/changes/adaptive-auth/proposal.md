## Why

The mode switch lets the voice lower Sutra and only the keyboard raise it. That is right for a laptop and wrong for a device with no keyboard, and it leaves no way to protect specific sensitive actions. A fixed spoken password can be overheard once and replayed forever. What Sutra has that nobody else has is the user's own recent history with it.

## What Changes

- **Questions from the user's own recent activity.** A one-time question about something the user said, typed, scheduled or planned in the last week ("What did you ask me to remind you about on Tuesday?"). It is different every time, and every fact used, right or wrong, is retired, so an overheard question and answer is useless later.
- **Grounded, not invented.** The question writer must pick a real recorded fact and take its answer from that fact's own words; code checks the answer is really there and does not appear in the question. Anything it cannot ground is discarded.
- **Judged for meaning.** A separate, tools-off judge sees only the question, the true answer and what was said, and returns match, no match or unsure; unsure is a fail. An exact match needs no model. A labelled set of answers, including paraphrases and attacks, must show zero false accepts.
- **What passing unlocks.** Going from limited mode back to full by voice (one question), and a timed grant (ten minutes) for protected gateway tools (two right out of three). The original request is not carried out automatically; the user asks again.
- **Failing is a signal.** One wrong answer gets a retry on a different question; two wrong answers drop Sutra to limited mode and start a cooldown. Not enough recent facts means Sutra says it cannot verify and points to the keyboard; it never makes up weak questions.
- **The distress phrase works as an answer.** Answering with it looks like success but leaves Sutra in limited mode.
- **One flipper.** `SUTRA_AUTH` (off by default), changed at runtime with `/auth on|off` or a key; turning it off needs the keyboard. With it off, nothing here runs.

Not defended against: people who live with the user and know their day. Out of scope by decision.

## Capabilities

### New Capabilities
- `adaptive-auth`: one-time questions drawn from the user's own recent activity, judged by meaning, behind a feature flipper.

### Modified Capabilities
(none)

## Impact

- New package `orchestrator/src/sutra_orchestrator/auth/` and a local `auth.db` (owner-only).
- `Orchestrator` gains a challenge state, gates protected tools and the voice mode return when the flipper is on, and records which channel (typed or spoken) each turn came by. `SafetyService` gains one authenticated way to raise the mode.
- Two small model calls per question (write, judge), and a judge call per answer unless it matches exactly.
