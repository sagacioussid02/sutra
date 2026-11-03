## Context

`Orchestrator.respond(text) -> str` has no terminal dependencies, and the
README already promises a voice agent can call it directly. Confirm-first
actions are held by the gateway; the next user reply is classified affirm,
deny, modify or unclear, and only `affirm` triggers `gateway_confirm`.

Testing in text showed that flow works, and showed one voice problem: the
re-ask after an unclear reply reads the gateway's raw description verbatim
("Onboard a GitHub repo (owner/name) ... dry_run defaults to true. (repo=...)"),
which is fine on a screen and bad when spoken.

The target is a laptop microphone, one user at a time, cheap and simple to
run, per the project's hosting preferences.

## Goals / Non-Goals

**Goals:**
- Speak a request, hear the reply, on a laptop, end to end.
- Reuse `respond()` unchanged as the single turn operation.
- Make a misheard transcript unable to confirm an action.
- Keep STT and TTS engines swappable and local by default.

**Non-Goals:**
- Real-time streaming, barge-in, wake word, or LiveKit (a later change).
- Hardware (Pi 5, ReSpeaker) and speaker identification.
- Any gateway change.

## Decisions

**Enter to start, end-of-speech detection to stop.** Press Enter once. A
loudness-based endpoint detector learns the room's noise floor, treats a few
loud blocks as speech, and ends the turn after about 1.2 seconds of quiet.
This replaced the original press-Enter-to-stop after live testing showed it
felt wrong. After a reply, conversation mode keeps listening for the next
sentence and returns to idle after a few quiet seconds. Known limit: it
detects silence, not meaning, so a long thinking pause can cut you off
(raise `SUTRA_SILENCE_MS`). Semantic end-of-turn detection, as ChatGPT voice
does, is a natural upgrade (a streaming transcription session with semantic
turn detection, or a small end-of-turn classifier) and belongs with the
ambient-presence change. Still no global hotkey: it needs accessibility
permissions.

**Two interfaces: `Transcriber` and `Speaker`.** `Transcriber.transcribe(audio)
-> Transcript(text, confidence)` and `Speaker.say(text)`. The loop depends
only on these, so tests use scripted fakes and engines can be swapped without
touching the loop.

**Cloud speech by default, local speech one key away.** OpenAI
`gpt-4o-transcribe` gives better accuracy than a small local model, and
`gpt-4o-mini-tts` is steerable on tone, which matters for a human feel.
Because the user will discuss personal matters, a private mode swaps both
engines for local Whisper (`faster-whisper`) and macOS `say` at runtime (`p`),
or at start with `SUTRA_VOICE_MODE=private`. Without an OpenAI key, voice
starts private. Private mode covers audio and spoken text only; the transcript
still goes to the Claude model, which is the brain, and memory is separate.
This limit is stated in the README rather than hidden.

**Persona is prompt, not code.** `persona.md` is appended to the system prompt
when voice runs. It gives the assistant a configurable name, tells it to
behave like another person in the room, allows at most one natural filler per
reply, and explicitly overrides the earlier "do not narrate tool use" rule
only for short natural phrases. The honesty and confirmation rules are
restated as still binding, so sounding human cannot mean guessing a number.
The name is also given to the transcriber as a hint so it is heard correctly.

**Automatic filler only when slow.** If `respond()` has not returned after a
short delay (default 1.5s), a rotating line ("Hmm, one sec.") is spoken, so
quick answers have none and slow tool calls do not leave dead air. A lock
keeps filler and reply from overlapping.

**Confirmation safety lives in the voice layer, not the model.** Before a
reply to a pending confirmation is passed to `respond()`, the voice loop
checks the transcript. If the transcript is empty, or its confidence is under
a configurable threshold, the loop does not call `respond()`; it re-asks.
That keeps the existing guarantee that only an `affirm` classification
confirms, and adds the guarantee that a doubtful transcript never reaches the
classifier as a yes. Confidence comes from the engine's own scoring: the geometric-mean token
probability for OpenAI, and mean log-probability scaled by speech probability
for local Whisper. The scales differ (a clear local sentence scored about
0.67), so the default threshold of 0.5 must be tuned by testing.

**Read back what was heard.** The transcript is printed for every turn, and
for a pending confirmation it is also spoken ("I heard: yes") so a mishearing
is caught before it matters.

**Speak a rephrased re-ask.** The orchestrator's unclear-reply re-ask
currently reuses the gateway description. For voice, the re-ask is rephrased
to a short question ("Sorry, was that a yes or a no?") and the description is
not read again. This is a small change to the orchestrator's re-ask text,
gated so the typed REPL keeps its current output.

**No audio persistence by default.** Audio is held in memory for the turn and
dropped. An opt-in setting writes recordings to a directory for debugging.

## Risks / Trade-offs

- **Misheard confirmations.** Even with a confidence gate, STT can turn "no"
  into "go". Mitigated by the readback and the threshold, and by keeping
  `never-by-voice` tools unavailable here as today. Residual risk is real, so
  the first voice tests use the minions `onboard_project` dry run only.
- **Latency.** Local Whisper plus a model call plus a tool call may take
  several seconds per turn. Acceptable for push-to-talk; streaming is the
  later fix.
- **Private mode accuracy.** The local base model mishears more than the
  cloud model; its size is configurable.
- **Cloud data exposure.** In cloud mode, audio and spoken replies go to
  OpenAI under its API data terms, which should be reviewed. Private mode is
  the mitigation, and it is a manual switch, so forgetting it is a risk.
- **macOS microphone permission.** The first run will prompt; denial must
  produce a clear error, not silence.
- **Echo.** The assistant's speech could be picked up by the mic. Push-to-talk
  avoids this because recording only runs while the user holds the turn.

## Later: ambient presence (not built here)

The user wants an assistant that is always listening like a person in the
room, answers to its name without a wake word, and asks before speaking out
of turn. That is a different system from push-to-talk and gets its own
change. The seams left for it:

- `Recorder` is an interface, so a continuous stream with voice-activity
  detection can replace press-Enter recording.
- Deciding whether speech is addressed to the assistant should be a small
  classifier step before `respond()`, in the same style as the confirmation
  classifier: it sees only the transcript and recent context, never tool
  results. Addressing is cheap to check by name plus conversational context.
- Speaking out of turn (proactive notices) should go through the same
  permission idea as confirm-first: the assistant first asks "do you have a
  second?" and speaks only after a clear yes.
- Always-listening in cloud mode would stream room audio to OpenAI, which is
  a much bigger privacy decision than push-to-talk. It should default to local
  speech-to-text and keep audio on the machine until the user opts in.
- Echo handling is required: the assistant must not transcribe its own voice.
  Push-to-talk avoids this; continuous listening needs echo cancellation or
  muting during playback.
