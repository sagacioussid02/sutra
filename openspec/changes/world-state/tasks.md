## 1. Snapshot core

- [x] 1.1 Define the snapshot type: fields with value, source, observed-at, TTL, and stale flag; the field registry with per-field TTL configuration
- [x] 1.2 Implement the provider: assemble on first read in a turn, reuse within the turn, in-memory cache bounded by the shortest TTL; no database
- [x] 1.3 Implement per-source timeouts: a slow or failing source contributes no field and never blocks assembly
- [x] 1.4 Tests: assembly returns stamped fields; a field past its TTL is flagged stale; a failing source yields an absent field, not an error or a guessed value

## 2. Fields

- [x] 2.1 Presence hint field: user-set value with a control command to view and change it; shown with its set-time
- [x] 2.2 Calendar field: now/next events read through the existing calendar tools, 5-minute TTL
- [x] 2.3 Finance pointer field: when the finance snapshot tool was last read this session (finanxe returns no snapshot timestamp of its own); no figures copied
- [x] 2.4 Commitments field: pending confirmations, unanswered offers, active reminders, and episode-graph open items, read from their owning stores
- [x] 2.5 Fresh-events field: unexpired, relevant events from `inbound-events`, labelled untrusted
- [x] 2.6 Tests: each field reads only the current user's data (depends on `per-user-identity`); the finance field contains no figures; commitments reflect a just-created reminder and a just-resolved one

## 3. Consumption

- [x] 3.1 Implement the prompt rendering: compact block, ages inline, stale fields marked, character budget enforced like recall's
- [x] 3.2 Add a max-age read for code paths that need guaranteed freshness (for example before a confirm-first action), re-assembling only the demanded field
- [x] 3.3 Adopt the snapshot in the offers judge (it now sees open commitments and presence); the judge never assembled these by hand, so nothing was replaceable
- [x] 3.4 Tests: the rendered block shows an expired field as stale with its age; the judge's existing scenarios pass on the snapshot; a max-age read refreshes only the demanded field

## 4. Control and docs

- [x] 4.1 Add a `/state` control command showing the current snapshot exactly as consumers see it, with ages
- [x] 4.2 Add `SUTRA_WORLDSTATE` switch and document all new `SUTRA_*` variables in `orchestrator/.env.example`
- [x] 4.3 README section: what the snapshot contains, what it never contains, and the staleness rules
- [x] 4.4 Manual check: start a session, set a presence hint, create a reminder, and confirm `/state` and a reply both reflect them with plausible ages
