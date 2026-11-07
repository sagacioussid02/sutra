## 1. Speaker signal

- [ ] 1.1 Define the utterance speaker signal (speaker id or unknown, confidence, method) and attach it to the existing utterance path; text input carries the session user without a signal
- [ ] 1.2 Choose and integrate the identification implementation behind the signal interface (local-first; evaluate on the owner's voice for latency and accuracy, record the choice in the change notes)
- [ ] 1.3 Tests: enrolled speaker identified above threshold; unenrolled voice returns unknown; identification runs without adding a network dependency beyond the chosen implementation

## 2. Enrolment

- [ ] 2.1 Implement the enrolment flow: explicit command, a small number of short samples, profile stored locally owner-only under a user-chosen label mapped to a `per-user-identity` user id
- [ ] 2.2 Add control-surface listing and deletion of enrolled speakers; deletion takes effect on the next utterance
- [ ] 2.3 Tests: nobody is enrolled by being overheard; a deleted profile immediately stops identifying; profiles are never included in model prompts

## 3. Addressee detection

- [ ] 3.1 Implement the deterministic pre-filter: no open conversation (name not spoken) means nothing is addressed; push-to-talk counts as addressed
- [ ] 3.2 Implement the tools-off addressee classifier (utterance, speaker signal, conversation state → addressed / elsewhere / unclear), called only when the pre-filter passes
- [ ] 3.3 Implement the turn gate with the asymmetric rule: acting requires addressed; answering allows addressed or unclear; elsewhere never proceeds
- [ ] 3.4 Tests: side conversation in an open session triggers no tools, offers, or replies; a direct question is answered; unclear speech is answered but cannot invoke a tool

## 4. Confirmation binding

- [ ] 4.1 Point the orchestrator's confirmation check at the signal: speaker must match the claim's binding and confidence must meet the configured threshold
- [ ] 4.2 Audit confirmation-shaped utterances from a different or unknown speaker that were ignored for a claim
- [ ] 4.3 Tests: the bound speaker confirms; a different enrolled speaker cannot; an unknown speaker cannot; low confidence cannot; behaviour with the feature switch off is byte-identical to today

## 5. Config, docs, verification

- [ ] 5.1 Add the feature switch and confidence threshold configuration; document every new `SUTRA_*` variable in `orchestrator/.env.example`
- [ ] 5.2 README section: the interaction model, enrolment scope and how to revoke it, and the recorded spoofing risk
- [ ] 5.3 Manual check with a real setup: enrol the owner, open by name, hold a side conversation with another person in the room, then ask a question and confirm a harmless action end to end
