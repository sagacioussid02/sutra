## 1. Lanes

- [x] 1.1 Lanes via `Orchestrator.fork()`: a separate history and held action over the same gateway, model and memory (simpler than extracting a `Lane` class; `respond` is unchanged)
- [x] 1.2 Add a lane registry with a cap on background lanes and per-lane tool-call limits
- [x] 1.3 Tests that tool-call history stays valid with two lanes running together

## 2. Detach on speech

- [x] 2.1 Keep the microphone open during processing; detect speech onset while a lane is running
- [x] 2.2 Detach the running lane and route the new utterance to the foreground lane
- [ ] 2.3 (NOT BUILT YET) Add a cancel path ("never mind that")

## 3. Wait notice

- [x] 3.1 Spoken wait notice after a configurable delay, only when the loop can listen
- [x] 3.2 Keep the short filler for short waits; test both

## 4. Announcements

- [x] 4.1 Notification queue for finished lanes
- [x] 4.2 Ask-first flow, with a natural-gap rule when the user is mid-conversation
- [x] 4.3 "What came back" retrieval; add results to the foreground history as notes

## 5. Confirmations across lanes

- [x] 5.1 Single pending action across lanes; queue any further ones
- [x] 5.2 Spoken readback names the task; a yes applies only to the action just asked about
- [x] 5.3 Tests: overlapping confirmations, a stray yes, expiry, background lane hitting confirm-first

## 6. Barge-in (optional)

- [ ] 6.1 (DEFERRED: no headphones; revisit on the Pi with an echo-cancelling mic array) Stop playback on sustained speech when `SUTRA_BARGE_IN=on`; document headphones
- [ ] 6.2 Test that it stays off by default

## 7. Verification

- [ ] 7.1 Manual: ask a slow question, ask another meanwhile, accept the announcement
- [ ] 7.2 Manual: start a confirm-first action in the background and confirm it by voice
- [ ] 7.3 Update README and roadmap
