## Why

Sutra makes the same kinds of mistakes repeatedly unless someone edits its prompts: a phrasing the user always corrects, a suggestion type that's always ignored, a clarification it should have asked and didn't. A self-learning loop would notice those patterns — from corrections, and from which proactive suggestions were accepted versus ignored — and get better over time instead of waiting for a human prompt-editing session.

**Status: stub — not implemented. This is the riskiest change in the roadmap. It is gated on the reminders + direct-answers changes (A+B) being dogfooded first, and on Sidd's explicit go-ahead.**

## What Changes (planned)

- A reflection pass over episodes that produces **proposed lessons**: short, specific, inspectable statements ("when Sidd asks for a restaurant, he means somewhere the kid can go too"). Lessons are proposals only — each one waits for Sidd's explicit approval before it takes effect, exactly like a memory he can review, correct, or reject. Nothing about this loop ever modifies the system prompt, the code, or its own rules without that approval; there is no unreviewed self-modification, ever.
- Approved lessons are stored and loaded like memories (same store, same inspection and deletion commands), so the complete set of "things Sutra has learned to do differently" is always listable and removable.
- Before an approved lesson is promoted to always-on behaviour, it should pass the existing eval suites (classifier, extractor, recall) — a lesson that fixes one conversation and breaks the evals is not an improvement.
- Accepted-vs-ignored signals from proactive surfaces (interest resurfacing, idle research findings) feed the same proposal queue; an ignored suggestion type is evidence for a "stop suggesting this" lesson, proposed the same way and approved the same way.

## Capabilities

### New Capabilities

- `self-learning`: proposed, human-approved behavioural lessons derived from corrections and suggestion outcomes. (Stub — no spec yet; the spec is written when this change is picked up.)

## Impact

None yet — stub only. When picked up: expected to build on episodes, the memory review flow, and the eval harnesses. The approval gate and the no-self-modification rule are the design, not details to settle later — any future spec for this change that weakens them is a different change and needs its own explicit go-ahead.
