## Why

Sutra is accurate and polite, and still flat. A person is occasionally funny, and the right kind of funny differs from person to person. A line in the prompt that says "be funny" gives jokes at the wrong moments and no way to find out what lands. Humor needs a starting set, rules for when never to try, and a way to learn from the user's reactions.

## What Changes

- **A humor profile with dials.** A `level` (0 to 10, default 3: about one eligible turn in eight), a `variety` (how willing it is to try a style that has not worked yet), and five styles with a score each: dry understatement, light self-deprecation about being an AI, gentle teasing, wordplay, and absurd comparison. Teasing starts lower.
- **Rules in code, not in the prompt.** Humor is never offered on a turn that uses a tool, while an action awaits confirmation, after money, health, family trouble or loss comes up, when the user sounds frustrated or upset, on a doubtful transcript, or too soon after the last attempt. A turn that is allowed gets a short note naming one style and telling the model to skip it if it does not fit naturally.
- **Learning from reactions.** After a turn where humor was offered, one small call reads whether a joke was actually made and how the user reacted (laughed, smiled, neutral, groaned, annoyed, or told it to stop). Scores move by small bounded steps, the level drifts by at most one step per ten judged jokes, and "stop joking" sets the level to zero.
- **Control.** "Be funnier", "fewer jokes" and "no jokes" work by voice through a bounded tool; `/humor` shows the profile and lets the user set the level, variety, individual styles, or reset. `SUTRA_HUMOR=off` removes it.

"Temperature" is kept separate from the model's sampling temperature: higher sampling temperature makes replies random, not funnier. The humor dial that plays that role here is `variety`.

Out of scope: humor in other languages (it comes with Hindi), jokes about the user's third parties, and any change to factual or confirmation behaviour.

## Capabilities

### New Capabilities
- `personality`: a learned, bounded, rule-gated humor profile.

### Modified Capabilities
(none)

## Impact

- New package `orchestrator/src/sutra_orchestrator/personality/` and a small local `personality.db` (owner-only).
- `Orchestrator` gains an optional personality provider: a note for eligible turns, a background reaction check on the following turn, and one reduce-or-raise tool.
- One small model call, only after a turn where humor was offered.
