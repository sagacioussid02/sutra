## Context

`Orchestrator.respond` is a single serial conversation: one history, one held
action, and a tool-call history that must stay well-formed (every tool_use
answered by a tool_result in the next message). Running two `respond` calls at
once on it would interleave messages and break that. The voice loop is also
serial: record, think, speak, with the microphone closed while thinking.

## Goals / Non-Goals

**Goals:**
- Listen while working, so the user can ask something else or interrupt.
- Never lose or corrupt in-flight work when the user speaks.
- Never speak unprompted without asking first.
- Keep every confirmation guarantee exactly as it is.

**Non-Goals:**
- Deciding whether speech is addressed to Sutra (separate change).
- Echo cancellation. Barge-in is headphones-only for now.
- Cross-task planning or dependencies between tasks.

## Decisions

**Lanes, not a re-entrant orchestrator.** A `Lane` owns a history, a held
action and a status; the gateway, model, classifier and memory are shared.
`Orchestrator` becomes the foreground lane plus a registry of background
lanes. A detached request keeps its own lane, so tool-call history stays valid
by construction.

**Interruption means detach, not cancel.** When speech starts while a lane is
processing, that lane keeps running as a background task. The user hears
nothing about it until it finishes. If the user says something like "never
mind that", a cancel path stops the lane before it finishes.

**The new utterance starts from the conversation so far.** The foreground lane
continues the main history. A detached lane started from a snapshot of that
history plus its own utterance; its result is later added to the foreground
history as a note, so Sutra can refer to it.

**Wait notice.** If a request is still running after a few seconds, Sutra says
once that it is working on it and that the user can ask something else. This
replaces the generic "hmm, one sec" for long waits; the short filler stays for
short ones. The notice is only said when the loop really can listen, so it is
never an empty promise.

**Ask first, then speak.** Finished background work goes to a notification
queue. If the user is idle, Sutra asks permission to share it. If the user is
mid-conversation, it waits for a natural gap (end of a reply with no speech for
a moment). A yes plays the result; a no or later keeps it queued; "what came
back" retrieves it. The ask is spoken by Sutra but the decision is the user's,
and an unclear reply is treated as not yet.

**Confirmations stay single and explicit.** A background lane may call
read-only tools. When it requests a confirm-first tool the gateway holds it as
today, the lane pauses, and a notification asks the user. Only one action is
awaiting confirmation across all lanes; a second is queued. A reply is
interpreted as an answer only when Sutra has just asked about that action, and
the confirm call is made by orchestrator code after the intent classifier says
affirm, never by a model. A "yes" meant for something else therefore cannot
confirm a queued action.

**Concurrency cap.** At most two background lanes. A third request is told
"I'm already working on a few things, give me a moment".

**Barge-in is opt-in and deferred.** It is not built in the first pass because the target laptop has no headphones; the Pi with an echo-cancelling mic array is where it belongs. With `SUTRA_BARGE_IN=on`, speech detected during
playback stops playback and the user's words are handled as the next turn. The
remainder of what Sutra was saying is dropped. Off by default because
speaker-to-mic echo would make Sutra interrupt itself. Detection while playing
uses a higher loudness threshold and requires sustained speech.

## Risks / Trade-offs

- **Misrouted yes.** The main danger is a "yes" attaching to the wrong pending
  action. Mitigated by one pending action at a time, spoken readback of what
  is being confirmed, and the unchanged classifier gate. Tests must cover
  overlapping confirmations.
- **Cost and rate limits.** Parallel lanes multiply model calls. The cap and a
  per-lane tool-call limit contain it.
- **Confusion.** Several things in flight can be hard to follow by ear. Sutra
  names the task when it announces ("the twin health check").
- **Echo.** Without headphones, barge-in will misfire; it is off by default and
  documented.
- **Memory.** Background lanes feed memory extraction too, so notes about the
  user could be recorded twice. Extraction must be idempotent per utterance.
