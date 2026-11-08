## 1. Shared turn events

- [ ] 1.1 Factor the turn processing in `Orchestrator` so a turn yields an event stream — text deltas, tool-call started/finished with outcome, confirmation pending, offer created/deferred, turn completed/failed — with `respond()` becoming the assembling consumer it already behaves as; the REPL and the voice client move onto the stream with no visible change
- [ ] 1.2 Tests: the existing suite passes unmodified in behaviour — in particular the voice path's sentence-splitting consumption and lead-in rules; a scripted session produces identical final replies through the old contract and the event stream

## 2. Chat server

- [ ] 2.1 Implement the `chat` package server: a turn endpoint plus a server-sent-events stream of the turn's events, token authentication as the orchestrator already requires, localhost the default bind; add `SUTRA_CHAT` settings (enable, bind, port, debug default) and document them in `orchestrator/.env.example`
- [ ] 2.2 Implement the transcript store: per-user, schema-versioned local SQLite at 0600, recording user turns, replies, tool actions with outcomes, and confirmation states; a control command to view and clear it; the store is never read by recall
- [ ] 2.3 Tests: an unauthenticated request is rejected; the default bind accepts only local connections; a gateway outage surfaces an unavailability report and no fabricated reply; a turn interrupted mid-stream completes no confirm-first action and is marked failed in the transcript

## 3. Chat UI

- [ ] 3.1 Ship the static single-page UI bundled with the package (no build step, no external assets): conversation history from the transcript store, incremental rendering of a streaming reply, distinct renderings for tool actions and a pending confirmation, and slash commands passed through to the existing command handlers
- [ ] 3.2 A pending confirmation is answered by typing only: the UI renders its state and what is being confirmed, and offers no control that confirms or denies without a classified reply
- [ ] 3.3 Tests: a scripted session through the endpoints — an ordinary question, a confirm-first action answered by typing, an offer raised — leaves a transcript whose actions and states match the session; reopening after a restart shows the same transcript

## 4. Debug toggle

- [ ] 4.1 Add the debug annotation view: per-session toggle, off by default, annotating turns from the turn events and the owning stores — confirmation consumption and classification, offer deferrals with the arbiter's recorded reason, stale snapshot fields
- [ ] 4.2 Tests: with the toggle on, a deferred offer's recorded reason is shown and a confirmation reply's classification is shown; with it off, neither is; the same scripted session produces identical decisions and outcomes with the toggle on and off

## 5. Identity, docs, and manual test

- [ ] 5.1 Name the user-resolution hook the turn endpoint uses; until `per-user-identity` lands it resolves to the single owner, and the README states that assumption plainly; the hook adopts the identity mapping when that change lands, with transcripts already keyed per user
- [ ] 5.2 README section: what the chat surface is for (dogfooding and testing), that it runs the same pipeline as voice, the single-owner assumption, and the debug toggle
- [ ] 5.3 Manual test script: with `SUTRA_CHAT` on, run a scripted session in chat — an ordinary question, a reminder created, a confirm-first action confirmed and one declined by typing, an offer deferred — then run the same script in the REPL and compare outcomes; toggle debug on and repeat one segment, confirming the annotations explain the deferral and the classifications
