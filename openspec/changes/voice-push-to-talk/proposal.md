## Why

The text orchestrator is proven against the gateway, including minions, twin
and finanxe, and its confirmation flow held up under yes, no, unclear and
modify replies. Sutra is meant to be talked to, and nothing yet lets you do
that. Voice is the next step on the agreed order (unify, then laptop-mic
voice, then hardware). Doing it as a thin push-to-talk loop around
`Orchestrator.respond()` tests the part that is actually new, speech in and
speech out, without taking on a real-time voice framework before it is needed.

## What Changes

- Add a push-to-talk voice client to `orchestrator/`: press Enter, speak,
  press Enter; the audio is transcribed, passed to `respond()`, and the reply
  is spoken aloud.
- Cloud speech by default: OpenAI `gpt-4o-transcribe` to hear and
  `gpt-4o-mini-tts` to speak, chosen for accuracy and a natural voice.
- A **private mode** that swaps both for local engines (local Whisper and
  macOS `say`) with one key, so personal conversations send no audio and no
  spoken text to OpenAI. Voice starts private if no OpenAI key is configured.
- Speech engines sit behind small interfaces so they can be swapped.
- A persona: the assistant has a configurable name and behaves like another
  person in the room, with natural fillers ("hmm", "okay, so") used sparingly,
  contractions, and short replies. A short spoken "hmm, one sec" is added
  automatically only when a reply is slow.
- Voice-specific confirmation safety for `confirm-first` tools: an empty or
  low-confidence transcript never reaches the confirmation path, what was
  heard is read back, and the re-ask is phrased for speech instead of reading
  the raw description aloud.
- No audio is stored unless the user turns that on.
- Designed for, but not built here: always-listening without a wake word,
  deciding whether speech is addressed to the assistant, and asking
  permission before speaking out of turn. See the design's "Later" section.
- Not in this change: LiveKit or streaming, barge-in, hardware, speaker
  identification, any gateway change.

## Capabilities

### New Capabilities
- `voice-push-to-talk`: a laptop-microphone push-to-talk client that turns
  speech into a `respond()` turn and speaks the reply in a human, named
  persona, with a private local mode and safeguards so a misheard transcript
  cannot confirm an action

### Modified Capabilities
(none)

## Impact

- New code under `orchestrator/` (a `voice` module and an entry point such
  as `python -m sutra_orchestrator.voice`). The gateway, twin, finanxe and
  minions are untouched.
- New optional dependencies: a `voice` extra (OpenAI SDK, audio capture) and
  a `voice-local` extra (local Whisper, with a model downloaded on first use).
- New optional `OPENAI_API_KEY`.
- New runtime needs: microphone permission for the terminal on macOS.
- In cloud mode, recorded audio and the text of spoken replies go to OpenAI.
  In private mode neither does. In both modes the transcript still reaches the
  Anthropic API as text, exactly like typed input, and memory behaves as before.
- Small changes to the orchestrator: an optional persona prompt, a
  speech-friendly re-ask, and a `cancel_pending()` method. Defaults keep the
  typed REPL unchanged.
- Depends on `text-orchestrator` and `assistant-memory`, both already built.
