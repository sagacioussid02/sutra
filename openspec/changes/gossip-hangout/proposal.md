## Why

The user built a separate project, a private group chat with three fictional friends (Priya, Rahul, Ananya) and an info bot, with its own social state and strategy learning. Sutra can be a way into it by voice, as a place to hang out, if it is kept clearly apart from the assistant: fiction is labelled as fiction, nothing the user says to Sutra flows into it without their say-so, and nothing it says flows back into what Sutra believes about the user.

## What Changes

- **A hangout mode.** The user starts it ("let's catch up with the group") and everything they then say goes, word for word, to the group chat. Each reply comes back with the speaker's name, and by voice each persona has its own voice. "Leave the group" ends it.
- **The user speaks for themselves.** The model never composes or forwards anything to the group, so it cannot pass on personal details by its own initiative. A message about money, health, loss, family or legal trouble is not forwarded at all; Sutra says it will keep that out of the group. A sign of distress ends the mode and Sutra listens as usual.
- **Fiction is labelled.** Entering says plainly that the group are fictional friends run in a separate app, that messages go to that app, and that its info bot may look up public facts online.
- **Kept apart from what Sutra knows.** Hangout turns are not written to memory, not added to the conversation graph, not shown to the lessons or interests passes, and carry no humor or unprompted offers. What the group says is never stored as something Sutra knows.
- **A seam, not a merge.** The group is reached through a small client for the app's REST API (`SUTRA_GOSSIP_URL`, off by default). It sits behind an interface so it can be replaced by gateway tools later.
- **Control.** `/hangout` shows the address and whether the app answers; `/hangout reset` starts the group's world afresh.

Out of scope: feeding Sutra's memory or graph into the group, anything about real third parties beyond what the user types in the group themselves, and changes to the gossip project.

## Capabilities

### New Capabilities
- `gossip-hangout`: a voiced, opt-in, clearly fictional group chat the user steps into, kept apart from Sutra's memory.

### Modified Capabilities
(none)

## Impact

- New package `orchestrator/src/sutra_orchestrator/hangout/`. The orchestrator gains a mode like interpreter mode; the voice loop speaks persona lines in their own voices; `OpenAISpeaker.say` accepts an optional voice.
- Outbound requests only to the configured local address.
