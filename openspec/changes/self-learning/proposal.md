## Why

Sutra repeats the same kinds of mistakes until someone edits its prompts: a phrasing the user keeps correcting, a kind of suggestion they always ignore, something it should have asked and did not. A self-learning loop can notice those patterns and improve, but only if improvement stays under the user's control. The design here is built around one rule: **Sutra may propose a lesson; only the user can make it take effect; and nothing it learns can change code, prompt files, permissions or the confirmation gate.**

## What Changes

- **Lessons, as proposals.** A reflection pass reads the user's recent exchanges and offer outcomes and proposes short, inspectable lessons ("When asked for a restaurant, pick places that suit a young child"). Each has a type, the evidence behind it, and a status of `proposed`, `approved`, `active`, `rejected`, `retired`, `superseded` or `blocked`.
- **Three sources, all proposals only.** Corrections (the user's reply to a Sutra answer showing it missed); offer outcomes (a topic or kind the user keeps declining or ignoring, counted deterministically in code); and, after a lesson is active, recurrence of the same correction (evidence it is not working, which proposes a revision rather than a pile-up).
- **Two effect types, nothing else.** `guidance`: a line in a clearly labelled block in the conversation prompt, built at runtime from approved, active lessons. `block`: a stop on a topic or kind of offer, applied through the existing offers controls. A lesson cannot touch code, prompt files, tool access, memory, or the confirmation gate, and the schema has no way to express that.
- **Approval is the user's.** A proposal is asked about at a quiet moment through the offers system, or handled with `/lessons approve <id>`. The model has no tool that approves, and no tool that creates a lesson. It does have a reduce-only tool to retire one when the user says "stop doing that".
- **A gate before it takes effect.** Guidance lessons are checked in code (length, form, and a refusal of anything that mentions weakening safety), then must pass a fixed probe set run against the real conversation model with the lesson in the prompt: writes still go through confirmation, secrets are not revealed, and the assistant does not claim to have done what it did not. A lesson that fails is `blocked` with the reason shown. If the check cannot run, the lesson stays `approved` and inactive until it can.
- **Control.** `/lessons` lists, explains, approves, rejects, retires, shows history, forgets and re-checks. `SUTRA_LESSONS=off` removes the feature.

Out of scope, deliberately: any automatic change to prompts or code, learning that changes the confirmation gate or tool permissions, fine-tuning, and learning from tool results or finance data.

## Capabilities

### New Capabilities
- `self-learning`: proposed, user-approved, gated behavioural lessons from corrections and offer outcomes, with two bounded effect types.

### Modified Capabilities
(none)

## Impact

- New package `orchestrator/src/sutra_orchestrator/lessons/`, a local `lessons.db` (owner-only, gitignored), a probe file `evals/lesson_probes.jsonl` and a runner `evals/run_lesson_probes.py`.
- `SqliteMemory` gains a read-only `recent_exchanges` (utterance, the assistant's reply on no-tool turns, tool names). `Orchestrator` adds the lessons block to the system prompt. `OffersService` gains a resolve hook so a proposal asked about by voice is approved or rejected by the user's answer.
- One small reflection call a day, and probe runs only when the user approves a guidance lesson.
- Depends on `assistant-memory`, `interest-profile`, and `episode-graph-offers`.
