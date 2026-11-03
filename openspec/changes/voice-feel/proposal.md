## Why

Sutra still feels like talking to a robot, and the biggest cause is time, not words. Today the whole reply is written before the first word is spoken, a "hmm, one sec" filler is itself a fresh text-to-speech round trip, and nobody can see where the seconds go. Delivery is also uniform.

## What Changes

- **Speak while it writes.** The reply is streamed from the model and spoken sentence by sentence, starting with the first complete sentence. Text before a tool call is never spoken half-finished, and the full reply is still what is recorded. Speaking over it (barge-in) works per sentence.
- **Instant acknowledgements.** Short phrases (the "hmm, one sec" fillers) are synthesized once, cached in memory, and replayed instantly; they are pre-warmed at start. The filler comes sooner and is varied.
- **Delivery you can tune.** The text-to-speech style instructions become a setting, with a warmer default, so the voice can be adjusted without code.
- **See the time.** With `--verbose`, each turn logs where the time went: hearing you, thinking, and getting to the first spoken word.

Out of scope: echo cancellation, a wake word, local text-to-speech streaming, and changing the models.

## Capabilities

### New Capabilities
- `voice-feel`: streamed spoken replies, instant cached acknowledgements, tunable delivery, and visible turn timing.

### Modified Capabilities
(none)

## Impact

- `AnthropicModel.complete` gains an optional text-delta callback; `Orchestrator.respond` gains an optional `on_text`; the voice loop speaks streamed sentences. All optional: text mode and existing callers are unchanged.
- `OpenAISpeaker` gains a short-phrase cache and `prewarm`.
- No database or gateway changes.
