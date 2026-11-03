## Why

Sutra records every conversation as an episode and extracts durable memories, but it has no model of what the user *cares about* as topics: that they asked about Halloween places last month is exactly the signal that a Diwali outing nearby is worth surfacing. Today that connection can only happen if the user asks. An interest profile — a small, inspectable set of topics with recency and strength, derived from episodes and memories — is what the proactive behaviours (topic resurfacing in conversation, idle research) would read.

**Status: stub — not implemented. This change is gated on the reminders + direct-answers changes (A+B) being dogfooded first, and on Sidd's explicit go-ahead.**

## What Changes (planned)

- A periodic reflection pass over recent episodes and active memories that proposes interest topics (with evidence: the episodes that support each one). Proposals land as memories through the existing reviewable memory path — visible, correctable, forgettable — never as a hidden profile file the user cannot inspect.
- A "related topic" resurfacing behaviour: when a conversation touches a topic near an existing interest, the assistant may briefly connect the two ("you asked about Halloween events last month — there's a Diwali festival this weekend"). Frequency-capped and easy to dismiss, so it stays a pleasant nudge rather than a nag.
- Privacy controls in the existing style: a switch to turn reflection off entirely, and the profile itself lives in the same store the user can already list, inspect, and delete from.

## Capabilities

### New Capabilities

- `interest-profile`: derived, inspectable interest topics from conversation history, plus in-conversation resurfacing of related topics. (Stub — no spec yet; the spec is written when this change is picked up.)

## Impact

None yet — stub only. When picked up: expected to build on the episode store and the memory extractor, add a scheduled reflection job (a consumer of the reminders change's scheduler), and add resurfacing hooks to the recall path.
