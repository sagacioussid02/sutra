## Why

Sutra answers explanation questions briefly on purpose, because long answers are hard to take in, especially by voice. That leaves the user with the short version of something they wanted to understand, and nothing brings them back to it. A good tutor would remember: "you asked me how tool calling works; now that you're building an agent, want a worked example?" Separately, a good assistant sometimes speaks up about something that has nothing to do with the current conversation but matters now: "snow is expected on the mountain road in about twenty minutes, and you mentioned driving up there."

Today Sutra forgets the moment a conversation moves on. The interest profile tracks broad tastes only, and its nudge is a fixed daily timer. Fixed timers are the wrong tool here: some topics deserve an offer after a few hours and many deserve none. Whether and when to speak should be judged, and the judgement should improve with how the user reacts.

## What Changes

- **A graph of conversation episodes.** Conversations are kept as nodes, each a coherent stretch of talk on one subject with a short gist and what was left unsaid (an example, going deeper, a decision still open). A linker subagent connects each new episode to earlier ones with typed, explained edges (same topic, extends, prerequisite of, applies to, updates). The graph is the shared memory for everything below.
- **A relatedness subagent.** While the user talks, a small tools-off subagent looks at the current conversation and the graph neighbourhood and returns *advice* to the orchestrator: nothing, or "this earlier episode is worth a follow-up now, here is the benefit". The subagent never speaks to the user; the orchestrator decides and asks.
- **Offers are judged, not scheduled.** There is no fixed cool-down, no "once a day" for conversation follow-ups, no per-thread limit. A judge weighs benefit against interruption, picks its own retry time, and compares its benefit score with a bar that moves with how the user has responded to past offers. Accepting lowers the bar; declining or ignoring raises it; "stop" is permanent for that topic or kind.
- **Two kinds of offer, one arbiter.** *Follow-up offers* come from the graph. *Timely offers* come from outside the conversation (a signal such as a weather warning, or a finished idle-research run) and are judged against what the graph says the user is doing or planning. One arbiter lets at most one proactive thing through at a time and stands in front of the existing interests nudge. Timely offers expire, so a snow warning is never spoken after the snow.
- **Conversational, not a form.** The judge also picks how to say it. Often it is a teaser question that fits the mood ("Want to hear something interesting about tool calling?", "I found something good about your Diwali trip, want it?"). When the content is low-stakes and plainly useful, Sutra may simply say it, the way a friend would, without asking first. Offers are only ever speech: nothing that acts, spends or changes anything is done without the normal confirmation. Yes delivers; "not now" defers; "no" closes; anything else carries on without a "was that a yes?" loop.
- **A grounded example.** On yes, the example is short, spoken-style, and built only from context actually present, never invented details about the user's projects.
- **Control.** `/graph` and `/offers` let the user see episodes, edges, offer history and the learned bars, and delete or reset any of it; "stop offering me examples" works by voice; a switch turns each part off. Only safety rails stay fixed in code.

Out of scope, deliberately: producing timely signals (weather, calendar, idle research belong to `idle-research` and gateway tools; this change defines the signal intake and judges what arrives), embeddings (the retrieval layer is an interface that can be swapped later), spaced-repetition quizzes, and changes to the memory or interests databases.

## Capabilities

### New Capabilities
- `episode-graph`: conversation episodes as nodes, typed explained edges between them, a linker that builds them, and a relatedness subagent that gives advice.
- `proactive-offers`: judged, learned, ask-first offers of two kinds (follow-up and timely), with one arbiter, soft answers, grounded delivery and user control.

### Modified Capabilities
(none)

## Impact

- New packages `orchestrator/src/sutra_orchestrator/graph/` (store, linker, retriever, advisor) and `.../offers/` (arbiter, judge, bars, signals, service, commands), with local `graph.db` and `offers.db` (owner-only, gitignored), following the reminders, agents and interests layout. Interests stay separate: they are broad approved tastes; the graph is what was actually discussed.
- `Orchestrator` gains optional `graph` and `offers` providers: a post-conversation linking step, a per-turn advice step, an offer note for the prompt, and a soft offer slot read at the start of the next turn. The interests nudge asks the arbiter for permission.
- Small-model calls in the background: episode summarising and linking (after an episode closes), advice (only when the retriever finds candidates and the subject has changed), judging (only when there is a candidate), and the intent classifier already in use. All on the cheap model with a daily cap on calls.
- Turns that used excluded tools (default `finanxe_`) never contribute. Tool results are never read by this feature.
- No gateway, twin, finanxe or minions changes.
- Depends on `direct-answers`, `assistant-memory` (episode record), `interest-profile` (nudge, approved interests) and, for timely signals' producers, the later `idle-research`.
