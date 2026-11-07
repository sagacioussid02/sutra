## Context

Sutra's voice work so far: push-to-talk (`voice-push-to-talk`),
background-task narration (`voice-background-tasks`), and an orchestrator
that binds each pending confirmation to the requesting speaker and will
only honour a confirmation from that same speaker. What is missing is
any trustworthy answer to "who just spoke?" and "was that for me?" —
both explicitly deferred by the earlier changes.

The user's stated interaction design makes both questions load-bearing:
the assistant's name is spoken once to open, then conversation is
continuous, with the assistant expected to stay out of talk that is not
addressed to it, like a person in the room. Speaker identification also
has a privacy edge in a household: enrolment is biometric-adjacent data,
and the project's posture is local-first, user-inspectable,
user-deletable — the same posture as `assistant-memory`.

## Goals / Non-Goals

**Goals:**
- Sutra responds to speech addressed to it and stays silent for speech
  that is not, in an open conversation.
- Confirmations are honoured only from the bound speaker, on a real
  signal rather than an asserted label.
- Enrolment is deliberate, per person, visible, and removable.
- Every failure mode degrades toward today's behaviour, never toward
  acting on weaker evidence.

**Non-Goals:**
- Naming unenrolled speakers, or distinguishing two unenrolled speakers
  from each other. `unknown` is a complete answer.
- Anti-spoofing/liveness. A recording of the owner's voice is a recorded
  risk, mitigated by confirm-first design elsewhere, not solved here.
- Continuous diarisation of ambient audio. Identification runs on
  utterances the pipeline already captured for transcription.
- Changing when reminders or offers may speak. This change decides who
  is speaking and whether speech is addressed to Sutra; proactivity
  policy stays with `proactive-offers`.

## Decisions

### The signal is data the orchestrator consumes, not a decision it trusts blindly
The voice pipeline produces `{speaker_id | unknown, confidence, method}`
per utterance. The orchestrator's confirmation check compares speaker id
against the claim's binding and requires confidence at or above a
configured threshold. The pipeline never decides "this confirms" itself.

*Why:* the binding and its audit already live in the orchestrator;
keeping the security decision there means the voice client can improve
its identification without touching the safety rule, and tests can drive
the rule with synthetic signals.

### Addressee is a classifier with an asymmetric default
A small, tools-off classifier (the pattern used for confirmation intent
and relatedness advice) sees the utterance, the speaker signal, and
whether a conversation is open, and returns addressed / elsewhere /
unclear. The gate's rule is asymmetric on purpose:

- Would act (tools, confirmations, writes): requires *addressed*.
  Unclear is not enough.
- Would only answer or offer: *addressed* or *unclear* may proceed;
  *elsewhere* never does.

*Why:* the costs are asymmetric. Answering a question that was meant for
someone else is a mild embarrassment; executing a tool call on one is a
real-world side effect. A deterministic pre-filter (conversation not
open → nothing is addressed until the name is spoken) runs before the
classifier so the common case costs no model call.

### Enrolment is a flow, not a side effect
Enrolment starts from an explicit command, records a small number of
short samples, and stores the resulting profile locally (owner-only,
gitignored) under a user-chosen label mapped to a `per-user-identity`
user id. The control surface lists enrolled speakers and can delete a
profile, which takes effect immediately. Nobody is enrolled by being
heard, and a profile is never created from conversation audio
opportunistically.

Default scope is the owner. Enrolling anyone else is one deliberate act
per person, done by the user — the design does not enrol a household by
default because voice profiles of other people are their data, and the
user may choose owner-only permanently.

### Unknown and low-confidence are first-class
An unknown speaker can listen in an open conversation only to the extent
the owner has allowed (default: their utterances are treated as
elsewhere for acting, and may be answered only if the conversation was
opened by an enrolled speaker who is still the active speaker). This is
conservative v1 behaviour and is configurable per installation, with the
default on the restrictive side.

## Risks / Trade-offs

- [Misidentification lets the wrong person confirm] → confidence
  threshold, binding comparison in the orchestrator, audit of rejected
  confirmation-shaped utterances, and confirm-first design unchanged:
  identification strengthens an existing gate, it does not replace the
  confirmation itself.
- [Addressee classifier answers household conversation] → elsewhere
  speech never reaches tools or replies; the asymmetric default; a
  visible "why did you respond?" path via the episode record.
- [Voice profiles are sensitive data] → local, owner-only storage;
  listed and deletable; never sent to a model as content; enrolment is
  opt-in per person.
- [Identification adds latency to every utterance] → identification runs
  on the captured utterance in parallel with transcription; the
  deterministic pre-filter keeps closed-conversation audio free.
- [A similar-sounding family member is misread as the owner] →
  confidence threshold plus the recorded risk; high-impact tools remain
  confirm-first regardless of speaker.

## Migration Plan

Ships behind a switch, off by default. With the switch off, utterances
carry no signal and the orchestrator behaves exactly as today. Turning
it on requires at least one enrolled speaker (the owner) — the enrolment
flow is part of first enablement. The client-asserted speaker label used
by earlier tests is replaced by the signal at the same seam.

## Open Questions

- Which identification implementation: a local embedding model or the
  transcription provider's speaker features? Decide on measured latency
  and accuracy with the owner's voice; the signal interface is the same
  either way.
- Should an enrolled non-owner speaker be able to open a conversation,
  or only join one the owner opened? Default in this design: any
  enrolled speaker can open; their tools and data resolve to *their*
  user id under `per-user-identity`.
