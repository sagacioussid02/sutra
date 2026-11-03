## 1. Setup

- [x] 1.1 Add `voice` and `voice-local` optional dependency groups to `orchestrator/pyproject.toml`
- [x] 1.2 Add voice config (engines, models, voice, name, confidence threshold, filler delay, private start, recording directory) and document it in the README
- [x] 1.3 Add the `python -m sutra_orchestrator.voice` entry point

## 2. Interfaces and fakes

- [x] 2.1 Define `Transcript`, `Transcriber`, `Speaker`, `Recorder`, `Engines`, and `VoiceError`
- [x] 2.2 Write scripted fakes for use in tests

## 3. Engines

- [x] 3.1 Microphone recorder with a clear error on open failure and on pure-silence recordings
- [x] 3.2 OpenAI transcriber with a confidence score from token log-probabilities
- [x] 3.3 OpenAI speaker with steerable tone
- [x] 3.4 Local Whisper transcriber and macOS `say` speaker for private mode

## 4. Voice loop

- [x] 4.1 Record, transcribe, print transcript, call `respond()`, speak reply
- [x] 4.2 Skip empty or wordless recordings
- [x] 4.3 Gate low-confidence transcripts while an action is pending: re-ask, keep it held, drop at the re-ask limit
- [x] 4.4 Speak back what was heard before acting on a confirmation reply
- [x] 4.5 Private/cloud toggle, and private start when no key is set
- [x] 4.6 Automatic filler when a reply is slow, without overlapping speech
- [x] 4.7 Optional audio recording to a directory; none by default

## 5. Orchestrator changes

- [x] 5.1 Persona prompt with a configurable name, appended to the system prompt
- [x] 5.2 Speech-friendly re-ask that omits the raw description; typed output unchanged
- [x] 5.3 `cancel_pending()`

## 6. Tests

- [x] 6.1 Loop tests: question, empty recording, no words, quit
- [x] 6.2 Confirmation gate: low confidence, clear yes with readback, repeated doubtful replies
- [x] 6.3 Filler slow vs fast, private toggle, no-key start, audio saved only when enabled
- [x] 6.4 Engine tests: OpenAI confidence and arguments, error text hides details, silence detection, config validation
- [x] 6.5 Orchestrator tests: spoken re-ask, `cancel_pending`, persona in the system prompt
- [x] 6.6 Verify local Whisper end to end on generated speech

## 6b. End-of-speech and conversation mode

- [x] 6b.1 Endpoint detector with noise-floor calibration, speech onset, silence hangover, and timeouts
- [x] 6b.2 Auto-stop recording and hands-free conversation mode in the loop
- [x] 6b.3 Tests for short pauses, noisy rooms, clicks, nobody speaking, and conversation turns
- [x] 6b.4 Clear OpenAI key/permission/quota error messages

## 7. Manual verification (needs a microphone and an OpenAI key)

- [ ] 7.1 Voice-test a read-only minions question end to end in cloud mode
- [ ] 7.2 Voice-test the `onboard_project` dry run: yes, no, a mumbled reply, and a change
- [ ] 7.3 Repeat in private mode and compare accuracy and speed
- [ ] 7.4 Tune `SUTRA_MIN_CONFIDENCE` from observed scores; judge whether the persona and fillers sound natural
- [ ] 7.5 Update the top-level README roadmap

## 8. Follow-up change (not in this one)

- [ ] 8.1 Propose `ambient-presence`: always-listening, addressee detection, ask-before-speaking, echo handling, local-first audio
