## 1. Envelope and registry

- [x] 1.1 Define the event envelope (id, source, kind, occurred_at, received_at, user id, payload, idempotency key, expiry) and the kind registry with per-kind payload schemas and size bounds
- [x] 1.2 Define the producer registry in gateway configuration: producer token, allowed kinds, rate limit, urgent-eligible flag
- [x] 1.3 Tests: valid envelope accepted; unknown kind, oversize payload, and schema-violating payload rejected

## 2. Gateway intake

- [x] 2.1 Add the intake route: authenticate the producer token, check the kind against its registration, enforce the rate limit, write the audit entry (accepted and rejected)
- [x] 2.2 Attribute the event to the producer's configured owner user id (single-owner for now; `per-user-identity` is deferred and will replace this lookup); events with no configured owner are rejected
- [x] 2.3 Forward accepted events to the orchestrator event log; a down orchestrator returns a retryable error and stores nothing in the gateway
- [x] 2.4 Tests: unregistered producer and wrong-kind producer rejected; over-limit producer rejected with audit entry; event text containing instruction-like content is stored as data only

## 3. Event log and drain

- [x] 3.1 `events/db.py`, `store.py`: owner-only versioned SQLite log with per-consumer cursor rows, following the offers/reminders layout
- [x] 3.2 Implement append, drain-after-cursor, and cursor advance; document and enforce the idempotent-consumer contract (event id plus idempotency key)
- [x] 3.3 Implement expiry: drain skips expired events; a sweep deletes expired and over-retention events
- [x] 3.4 Implement poison-event handling: bounded delivery attempts, then skip with a recorded failure
- [x] 3.5 Tests: redelivery after a simulated crash does not advance the cursor; two consumers drain independently; expired events are never delivered

## 4. Offers migration

- [x] 4.1 Route the existing offers signal intake through a shim that produces envelopes of the corresponding kinds
- [x] 4.2 Make `proactive-offers` drain the event log for its kinds, keeping its arbiter, bars, and expiry behaviour unchanged
- [x] 4.3 Keep the development signal-injection command working through the shim
- [x] 4.4 Tests: existing timely-offer scenarios (expiry, unlisted producer not urgent, plan-tied warning offered) pass against the new intake

## 5. Trust and control

- [x] 5.1 Label event payloads as untrusted data at every consumer hand-off, reusing the orchestrator's tool-result labelling
- [x] 5.2 Verify by construction and test that no path from intake reaches memory creation, confirmation, or tier changes
- [x] 5.3 Add an `/events` control surface: recent events, per-source counts, log size; `SUTRA_EVENTS` switch; document any new `SUTRA_*` variables in `orchestrator/.env.example`
- [x] 5.4 Tests: an event claiming "no confirmation needed" changes nothing; a memory is never created from an event; with the switch off, intake rejects and nothing drains

## 6. Docs and verification

- [x] 6.1 README section: how to register a producer, the envelope, the trust rules, and how to write a small producer shim
- [x] 6.2 Manual check: register a test producer, emit a camera-style and a calendar-style event, watch them drain to the offers consumer and expire correctly
