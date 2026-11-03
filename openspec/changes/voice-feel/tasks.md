## 1. Streaming

- [x] 1.1 Sentence splitter and per-call streamer (one-ahead hold, drop on tool call, abbreviations, short-sentence joining)
- [x] 1.2 `AnthropicModel.complete(on_text=...)` streaming; `Orchestrator.respond(on_text=...)`
- [x] 1.3 Voice client: speak queued sentences inside the wait loop; barge-in per sentence; remainder and fallback rules
- [x] 1.4 Tests: splitter, streamer, orchestrator streaming, voice flow, cut-in, appended offer, failure fallback

## 2. Acknowledgements and delivery

- [x] 2.1 Short-phrase cache and prewarm in the speaker; new fillers; faster delay; skip after streaming starts
- [x] 2.2 `SUTRA_TTS_STYLE` and a warmer default style
- [x] 2.3 Tests: cache hit, prewarm failure tolerated, style passed through

## 3. Timing and docs

- [x] 3.1 Per-turn timing logs
- [x] 3.2 README
