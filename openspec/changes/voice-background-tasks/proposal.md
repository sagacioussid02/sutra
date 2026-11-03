## Why

Live testing of push-to-talk showed it works but is not conversational. While
a slow tool call runs, Sutra is deaf and silent; the user cannot ask anything
else, and cannot interrupt. A person in the room would say "give me a minute
on that, ask me something else meanwhile", keep working, and come back with
the answer. This change adds that, and is the first real step toward the
always-present assistant described in the voice design.

## What Changes

- Keep listening while a request is being processed. If the user speaks, the
  request in flight is detached and keeps running as a background task, and
  the new utterance is handled right away.
- When a request is going to take a while, Sutra says so once, naturally, and
  invites another question while it works.
- Each task runs in its own conversation lane (own history and own held
  action) over the same gateway, model and memory, so concurrent work cannot
  corrupt each other's tool-call history.
- When a background task finishes, Sutra does not just start talking. It asks
  first ("I've got the twin health back, want it now?"), speaks the result
  only after a yes, and otherwise keeps it for "what came back?".
- Background tasks may use read-only tools freely. When one needs a
  confirm-first action, it pauses and asks the user, using the existing
  confirmation gate unchanged. At most one action is awaiting confirmation at
  a time, and a yes only ever applies to the action just asked about.
- Optional barge-in: interrupt Sutra while it is speaking. Off by default,
  because laptop speakers feed Sutra's own voice back into the microphone;
  intended for headphones.
- Not in this change: wake-word-free addressee detection (is this speech for
  me), proactive speech unrelated to a task, speaker identification,
  hardware.

## Capabilities

### New Capabilities
- `background-tasks`: concurrent conversation lanes, detaching an in-flight
  request when the user speaks, wait notices, and ask-first announcements of
  finished work

### Modified Capabilities
(none)

## Impact

- `orchestrator/`: the orchestrator becomes able to run several turns at once
  through separate lanes; the confirmation gate is unchanged and still the
  only caller of `gateway_confirm`.
- `orchestrator/voice`: the loop keeps the microphone open during processing
  and routes utterances to lanes.
- More model calls in parallel, so higher short-term cost and rate-limit
  exposure; a cap on concurrent tasks is part of the design.
- No gateway change.
