## Why

The voice interaction model the user asked for is: say the assistant's
name once to open a conversation, then talk continuously — no repeated
wake word. Two earlier changes deferred exactly what that model needs:
`voice-background-tasks` lists as not-in-scope "wake-word-free addressee
detection (is this speech for me), proactive speech unrelated to a task,
speaker identification", and the gateway design notes no
speaker-verification exists today.

Without it, continuous listening is unusable and unsafe: Sutra cannot
tell the user talking to it from the user talking to someone else in the
room, and it cannot tell the user from anyone else. The second half is
not theoretical — pending confirmations are already bound to the
requesting speaker in the orchestrator (merged as PR #1), but that
binding currently trusts whatever speaker label the client asserts. This
change supplies the real signal the binding consumes, and the addressee
judgement that decides whether an utterance is Sutra's business at all.

## What Changes

- **A speaker signal per utterance.** The voice pipeline attaches to
  every utterance a signal: enrolled speaker id, or `unknown`; a
  confidence; and how the identification was made. Text input is the
  session's user by definition and needs no signal.
- **Addressee detection.** Each utterance in an open conversation is
  classified as addressed to Sutra, addressed elsewhere, or unclear,
  using the conversation state (an open conversation after the name was
  spoken), the speaker signal, and a small classifier — never a tool.
  Speech addressed elsewhere never triggers tools, offers, or replies;
  unclear speech is treated as not addressed when it would act, and as
  addressed when it would only answer, so Sutra errs toward silence
  before action and toward helpfulness before silence.
- **Confirmations consume the signal.** A confirmation for a pending
  claim is accepted only from the speaker the claim is bound to, at
  sufficient confidence. A confirmation-shaped utterance from a different
  or unknown speaker is ignored for that claim (and noted in the audit),
  exactly as an expired claim is.
- **Enrolment is explicit and scoped.** A speaker enrols by a short,
  deliberate enrolment flow the user starts. The default scope is the
  owner only; enrolling another person (partner, family) is a separate
  deliberate act per person, by the user, and enrolment data is listed
  and removable from the control surface. Unenrolled voices are
  `unknown`, never guessed at.
- **Degradation is safe.** No signal, low confidence, or a disabled
  speaker feature leaves Sutra in today's posture: push-to-talk or an
  explicit open, and confirm-first actions require the existing
  text/classifier confirmation path.
- Out of scope, deliberately: identifying unenrolled people, diarising
  or transcribing recordings after the fact, any always-on cloud speaker
  service, liveness/anti-spoofing beyond a recorded risk, and any change
  to the spoken-reminder behaviour (whether reminders speak unprompted
  is a separate design decision, untouched here).

## Capabilities

### New Capabilities
- `speaker-addressee`: per-utterance speaker identification for enrolled speakers, addressee detection gating whether Sutra responds or acts, and confirmation binding that consumes the real speaker signal

### Modified Capabilities
(none — the orchestrator's speaker-bound confirmation behaviour already exists; this change supplies and specifies its input)

## Impact

- Voice client: speaker identification at capture time, the addressee
  classifier step, and the enrolment flow; signal attached to the
  existing utterance path into the orchestrator.
- Orchestrator: the confirmation check reads the signal's speaker and
  confidence instead of a client-asserted label; the turn gate consults
  addressee before tools or offers run.
- Builds on `voice-push-to-talk` and `voice-background-tasks` (which
  deferred this), and pairs with `per-user-identity`: an enrolled speaker
  maps to the same user id the gateway uses, so voice and data identity
  agree. Enrolment data is local, owner-only, and gitignored like other
  personal stores.
- No gateway, twin, or finanxe changes.
