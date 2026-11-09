## 1. Speaker signal

- [x] 1.1 Define the utterance speaker signal (speaker id or unknown, confidence, method) and attach it to the existing utterance path; text input carries the session user without a signal
- [ ] 1.2 Choose and integrate the identification implementation behind the signal interface (local-first; evaluate on the owner's voice for latency and accuracy, record the choice in the change notes)
- [x] 1.3 Tests: enrolled speaker identified above threshold; unenrolled voice returns unknown; identification runs without adding a network dependency beyond the chosen implementation

## 2. Enrolment

- [x] 2.1 Implement the enrolment flow: explicit command, a small number of short samples, profile stored locally owner-only under a user-chosen label mapped to a `per-user-identity` user id
- [x] 2.2 Add control-surface listing and deletion of enrolled speakers; deletion takes effect on the next utterance
- [x] 2.3 Tests: nobody is enrolled by being overheard; a deleted profile immediately stops identifying; profiles are never included in model prompts

## 3. Addressee detection

- [x] 3.1 Implement the deterministic pre-filter: no open conversation (name not spoken) means nothing is addressed; push-to-talk counts as addressed
- [x] 3.2 Implement the tools-off addressee classifier (utterance, speaker signal, conversation state → addressed / elsewhere / unclear), called only when the pre-filter passes
- [x] 3.3 Implement the turn gate with the asymmetric rule: acting requires addressed; answering allows addressed or unclear; elsewhere never proceeds
- [x] 3.4 Tests: side conversation in an open session triggers no tools, offers, or replies; a direct question is answered; unclear speech is answered but cannot invoke a tool

## 4. Confirmation binding

- [x] 4.1 Point the orchestrator's confirmation check at the signal: speaker must match the claim's binding and confidence must meet the configured threshold
- [x] 4.2 Audit confirmation-shaped utterances from a different or unknown speaker that were ignored for a claim
- [x] 4.3 Tests: the bound speaker confirms; a different enrolled speaker cannot; an unknown speaker cannot; low confidence cannot; behaviour with the feature switch off is byte-identical to today

## 5. Config, docs, verification

- [x] 5.1 Add the feature switch and confidence threshold configuration; document every new `SUTRA_*` variable in `orchestrator/.env.example`
- [x] 5.2 README section: the interaction model, enrolment scope and how to revoke it, and the recorded spoofing risk
- [ ] 5.3 Manual check with a real setup: enrol the owner, open by name, hold a side conversation with another person in the room, then ask a question and confirm a harmless action end to end

## Implementation notes (2026-11-08, PR in progress)

- 1.2 is **not** done here and is the deliberate gap: no identification
  implementation is chosen yet. The shipped `NullIdentifier` always
  returns `unknown`, adds no dependency, and sends nothing anywhere.
  Choosing a local embedding model vs the transcription provider's
  speaker features needs latency/accuracy measured on the owner's voice,
  on a real setup; the `SpeakerIdentifier` interface is the stable seam
  it drops in behind. Until then, an unidentified claim keeps today's
  voice posture (unknown may confirm a claim no identified speaker
  requested), so turning the feature on with the null identifier cannot
  break voice confirmations.
- 4.2 audit is deliberately narrow: only a yes-shaped utterance
  (deterministic fast path — "yes", "yeah") from a non-matching speaker
  is logged, because the gate never sends such a turn to the consent
  classifier, so anything subtler cannot be known to be a confirmation
  attempt. No audio, profile, or utterance text is logged.
- 5.3 is Sidd's manual check on a real setup, with his own voice.
- The `.env.example` fix for the `SUTRA_PATCHES_*` variables (missing
  since the propose-a-patch merge, which is why `test_env_example`
  failed on main) is included in this PR so the guard test passes.
