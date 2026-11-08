## 1. Occasions store

- [ ] 1.1 Implement the `occasions` package (`db`, `store`, `service`) following the `life` and `offers` layout: per-user entries with name, date rule, context line, observance notes, and source, in a schema-versioned local SQLite store with 0600 permissions
- [ ] 1.2 Implement date-rule evaluation: single date, annual month/day recurrence, lunar entry with a user-declared next-occurrence date; a lapsed lunar entry reports a needs-next-date state
- [ ] 1.3 Implement the delivery record: acknowledgment state keyed by occasion and occurrence date, written only when a carrying reply is returned
- [ ] 1.4 Tests: one user's occasions are never readable through another user's id; an annual occasion occurs again the following year; a lapsed lunar entry occurs on no date and reports needs-next-date; no code path creates an occasion from anything but a declaration, a confirmation, or a pack opt-in

## 2. World-state field

- [ ] 2.1 Register the occasion field with the world-state field registry: source the occasions store, TTL the end of the local day, value the occurring occasions with their observance notes; field absent when nothing occurs
- [ ] 2.2 Tests: a snapshot assembled on an occasion's day contains the field with its source; a snapshot on an ordinary day has no occasion field; the field never appears in the commitments list

## 3. Acknowledgment delivery

- [ ] 3.1 Add the turn-start delivery check in `Orchestrator.respond`, beside snapshot assembly: an undelivered occasion occurring today is rendered from its entry and attached at the head of the first ordinary turn's reply; the turn context records that the acknowledgment was made
- [ ] 3.2 A turn consumed by a pending confirmation does not carry the acknowledgment and does not record delivery; a day with no ordinary interaction records nothing and owes nothing
- [ ] 3.3 Tests: the first ordinary reply carries the acknowledgment and the second does not; delivery after an edit does not repeat; a confirmation-first day delivers on the later ordinary turn; the offer cap, the attention budget, and the offers store are untouched by a delivery; no reminder, offer, or commitment exists after a delivery that did not exist before

## 4. Control surface and packs

- [ ] 4.1 Add `occasions/commands.py` and register it in the existing command sets: list, add, edit, remove, and renew (set a lunar entry's next date); add the `SUTRA_OCCASIONS` switch and document it in `orchestrator/.env.example`
- [ ] 4.2 Ship one bundled cultural calendar pack as static data in the repo; opting in copies its entries into the user's store with the pack as source; there is no sync after the copy
- [ ] 4.3 Tests: commands round-trip an occasion end to end; an occasion removed before its day's first interaction is not acknowledged; a fresh store with packs available acknowledges nothing; a deleted pack entry is not restored; with `SUTRA_OCCASIONS` off, the turn-start check and the snapshot field are both inert

## 5. Follow-ons, docs, and manual check

- [ ] 5.1 Prompt guidance: suggestions arising from an observance are raised only as offers through the arbiter; principal-state edits are proposed, never applied, from an occasion
- [ ] 5.2 Tests: a follow-on suggestion counts against the offer cap and, declined, changes nothing — including principal state; an observance note alone leaves the next snapshot's availability unchanged
- [ ] 5.3 README section: what occasions are, that they are declared-only, the once-per-occurrence rule, and why a greeting is not an offer
- [ ] 5.4 Manual check: declare an annual occasion for today with an evening observance; confirm the first reply acknowledges it once, the second does not, `/state` shows the occasion field, and "keep the evening clear" arrives — if at all — as a declinable offer
