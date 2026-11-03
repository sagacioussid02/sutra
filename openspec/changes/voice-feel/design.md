## Context

A turn today: wait for the user to stop (1.2 s of quiet), transcribe, run the model to completion (possibly several tool steps), then speak the whole reply. Text-to-speech already streams audio, so what remains is the model wait before speech begins, and the extra TTS round trip for each filler.

## Decisions

**1. Stream sentences, one ahead.** The model client takes an optional callback for text deltas. The orchestrator wraps each model call in a streamer that splits the text into sentences (not on abbreviations such as "Dr." or "a.m.", and short sentences are joined to the next) and releases a sentence once the next one has begun to arrive, or the stream ends. If a stream ends with a tool call, whatever was held is dropped, so a half-finished thought before a tool call is never spoken. A single sentence of lead-in before a tool call is therefore never spoken. A longer lead-in speaks all but its last sentence; the voice client matches the final reply against the spoken sentences from any starting point, so nothing is said twice. Alternative: speak every delta as it arrives. Rejected: partial sentences sound broken and cannot be cut at a tool call.

**2. The reply is still whole.** `respond` returns the full reply as before and history records it. The voice client tracks what was spoken; whatever follows (an appended offer, or text that was never streamed) is spoken after. If the streamed text does not match the start of the reply, the whole reply is spoken, so nothing is lost.

**3. Streaming sits inside the existing wait loop.** The voice client's wait loop already listens for the user speaking during a slow request. When the first sentence arrives it stops listening (the same step a filler takes) and speaks sentences from a queue as they arrive, using the same speaking routine that supports speak-over. A cut-in ends the queue, and the model call is allowed to finish quietly so history stays consistent.

**4. Cached short phrases.** The speaker keeps the audio of phrases of up to 40 characters in memory after the first synthesis, replays them without a network call, and can pre-synthesize a list at start. The default fillers are re-worded to sound unrehearsed and the filler delay drops to 1.0 s. A filler is skipped once a streamed sentence has started.

**5. Delivery as a setting.** `SUTRA_TTS_STYLE` replaces the built-in style text when set. The default gains pacing and emotion guidance (varied pitch, shorter pauses, lighter on filler words).

**6. Timings.** Per turn, debug logs show: time to record and transcribe, time from request to reply, and time from request to the first spoken sentence. No new output without `--verbose`.

## Risks

- A streamed sentence is spoken before a later check could have changed the reply. The only later changes are appended text and fixed replies, which are handled as a remainder; the confirmation read-back is a normal model call and streams like any other.
- A bug in the streaming path must not make Sutra mute. If streaming raises, the whole reply is spoken the old way.
- Cached audio uses memory and a little startup time; it is capped at 24 phrases.
