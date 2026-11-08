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

## 5. Principal state

- [ ] 5.1 Principal-state store: per-user declared record (availability windows, daily attention budget in minutes, major commitments with end dates, effort-sensitivity preference) in a schema-versioned local SQLite store with 0600 permissions, following the memory stores' layout; entries carry their set-time and are never written from observed behaviour
- [ ] 5.2 Tests: round-trip of every field; one user's record is never readable through another user's id; a commitment past its end date reads as ended
- [ ] 5.3 Principal field in the snapshot: register the principal section in the field registry (source user-declared, observed-at = set or confirm time; TTL until changed for availability, budget, and effort sensitivity; the stated end date for commitments); assembly reads declared entries only, and renders the section with ages like every other field
- [ ] 5.4 Tests: the snapshot shows a declared budget with its age; nothing declared yields no principal section; an expired commitment renders as ended, not current; a stale principal field is excluded from budgeting but still rendered as stale
- [ ] 5.5 Arbiter consumption: offers carry an effort estimate (minutes + decision / review / hands-on kind); an offer estimated over the user's remaining budget is deferred in the offers store with the reason recorded, counted in the snapshot's commitments field, and scheduled for reconsideration at the next budget reset or commitment end; timed offers and reminders are placed outside declared unavailable windows
- [ ] 5.6 Tests: an over-budget offer is deferred — not presented, not dropped — and its deferral is visible; it resurfaces when the daily budget resets and when a blocking commitment ends; the existing four-a-day cap still applies on top of the budget; with no principal state declared, arbiter behaviour is byte-for-byte the old behaviour
- [ ] 5.7 Planner consumption: decomposition prefers steps the system can complete within its granted autonomy; a step that bills the user states its expected effort (minutes + kind) where the plan is presented
- [ ] 5.8 Tests: a plan with a user-billed step states that step's effort; given an autonomous alternative within autonomy, the plan takes it and bills nothing; a plan presented while principal state is absent carries no effort accounting and does not fail
- [ ] 5.9 Inspection and editing surface: extend `/state` to show the principal section exactly as consumers see it; add control commands to view, set, and clear each principal field; edits take effect at the next assembly
- [ ] 5.10 Tests + docs: an edit followed by an assembly reflects the change with a new set-time; document any new `SUTRA_*` variables in `orchestrator/.env.example`; README note on what principal state is, that it is declared-only, and the fallback when it is absent
- [ ] 5.11 Manual check: declare a small daily budget and a commitment ending tomorrow; confirm an expensive offer defers with its reason visible in `/state`, and that the offer resurfaces after the commitment ends
