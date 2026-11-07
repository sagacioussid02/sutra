## 1. Snapshot core

- [ ] 1.1 Define the snapshot type: fields with value, source, observed-at, TTL, and stale flag; the field registry with per-field TTL configuration
- [ ] 1.2 Implement the provider: assemble on first read in a turn, reuse within the turn, in-memory cache bounded by the shortest TTL; no database
- [ ] 1.3 Implement per-source timeouts: a slow or failing source contributes no field and never blocks assembly
- [ ] 1.4 Tests: assembly returns stamped fields; a field past its TTL is flagged stale; a failing source yields an absent field, not an error or a guessed value

## 2. Fields

- [ ] 2.1 Presence hint field: user-set value with a control command to view and change it; shown with its set-time
- [ ] 2.2 Calendar field: now/next events read through the existing calendar tools, 5-minute TTL
- [ ] 2.3 Finance pointer field: which finanxe snapshot is latest and when it was taken; no figures copied
- [ ] 2.4 Commitments field: pending confirmations, unanswered offers, active reminders, and episode-graph open items, read from their owning stores
- [ ] 2.5 Fresh-events field: unexpired, relevant events from `inbound-events`, labelled untrusted
- [ ] 2.6 Tests: each field reads only the current user's data (depends on `per-user-identity`); the finance field contains no figures; commitments reflect a just-created reminder and a just-resolved one

## 3. Consumption

- [ ] 3.1 Implement the prompt rendering: compact block, ages inline, stale fields marked, character budget enforced like recall's
- [ ] 3.2 Add a max-age read for code paths that need guaranteed freshness (for example before a confirm-first action), re-assembling only the demanded field
- [ ] 3.3 Adopt the snapshot in the offers judge, replacing its hand-rolled assembly; delete the replaced code in the same step
- [ ] 3.4 Tests: the rendered block shows an expired field as stale with its age; the judge's existing scenarios pass on the snapshot; a max-age read refreshes only the demanded field

## 4. Control and docs

- [ ] 4.1 Add a `/state` control command showing the current snapshot exactly as consumers see it, with ages
- [ ] 4.2 Add `SUTRA_WORLDSTATE` switch and document all new `SUTRA_*` variables in `orchestrator/.env.example`
- [ ] 4.3 README section: what the snapshot contains, what it never contains, and the staleness rules
- [ ] 4.4 Manual check: start a session, set a presence hint, create a reminder, and confirm `/state` and a reply both reflect them with plausible ages
