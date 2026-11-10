## 1. Dataset readiness

- [ ] 1.1 Confirm the `dogfood-feedback-loop` dataset meets the v1 floor: roughly 500–1,000 labelled turns, with a per-label minimum for every `speech_act` and `addressee` label (floor values recorded here once the label distribution is known); if unmet, this change waits — no substitute data sources
- [ ] 1.2 Implement the split: train / dev / held-out test partitioned by scenario (never by turn), fixed seed, split membership committed with the dataset version it was drawn from
- [ ] 1.3 Tests: no scenario id appears in more than one split; regenerating the split from the same dataset version and seed is byte-identical

## 2. Baseline measurement

- [ ] 2.1 Implement the baseline runner: the incumbent main-model judgements (addressee as in `speaker-addressee`; speech-act labels via a fixed, versioned prompt) over the held-out turns, scored by the same scorer the classifier will use
- [ ] 2.2 Produce the baseline report: per-class accuracy for both label sets and the headline metric (addressee false-positive rate — other-person/aside turns read as requests to Sutra)
- [ ] 2.3 Record the baseline report in-repo; it is the bar every model version is compared against

## 3. Training

- [ ] 3.1 Implement the training script under `orchestrator/training/`: inputs are a pinned dataset version and the split; outputs are the model artefact plus a training manifest (dataset version, split seed, script version, architecture, hyperparameters)
- [ ] 3.2 Train v1 once task 1.1's floor is met; architecture chosen against the latency budget and recorded in the manifest (boring by default — see design)
- [ ] 3.3 Tests: training is reproducible — same dataset version, seed, and script version produce an equivalent artefact and identical dev-set scores

## 4. Evaluation and the ship bar

- [ ] 4.1 Implement the eval runner: classifier over the held-out split, scored identically to the baseline; report includes per-class accuracy for both label sets, the headline metric, and a side-by-side baseline comparison
- [ ] 4.2 Measure inference latency on a Pi-class node (p50/p95 added latency per turn) and include it in the eval report
- [ ] 4.3 Apply the ship bar: ship only if the classifier beats the baseline overall AND on the headline metric AND meets the latency budget; otherwise commit the report as a negative result and leave the live path unchanged
- [ ] 4.4 Commit model artefact + manifest + eval report together under a model version; the runtime records the model version on every hint it emits

## 5. Orchestrator integration (advisory only)

- [ ] 5.1 Add the `classifiers/` package: artefact loader and local inference, no network calls; missing artefact or inference error means no hint, never an exception in the turn path
- [ ] 5.2 Attach the hint `{speech_act, addressee, confidences, model_version}` to the turn context; the `speaker-addressee` judgement may consume it as an input feature; the main prompt may present it as a fallible hint
- [ ] 5.3 Feature switch, off by default; document every new `SUTRA_*` variable in `orchestrator/.env.example`
- [ ] 5.4 Tests: with the switch off or the artefact absent, gate and confirmation behaviour is byte-identical to today; a deliberately wrong hint cannot authorise a tool call, cannot satisfy or block a confirmation, and cannot change the turn gate's asymmetric rule

## 6. Guardrails and docs

- [ ] 6.1 Add a guard test: no code path from the classifier package into the confirmation gate's decision, the scheduler, or tool authorisation (import/call-graph check, failing the suite if one appears)
- [ ] 6.2 README section: what the hint is and is not, the ship bar and where its eval report lives, how to disable or delete the model, and the standing invariant — the confirmation gate stays rule-based with its zero-false-affirm bar; learned models advise, never replace
- [ ] 6.3 Manual check (only if the bar is met): enable on a real setup, hold a side conversation and make an aside mid-conversation, and confirm from the episode record that hints were produced, were advisory, and that behaviour matched the gate's rules
