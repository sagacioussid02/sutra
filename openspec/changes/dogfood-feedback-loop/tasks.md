## 1. Sandbox profile and runner

- [ ] 1.1 Add a sandbox profile: throwaway stores for memory, episodes, lessons and offers; synthetic users; a controllable fake clock; a startup guard that aborts the run if the profile is not the sandbox profile
- [ ] 1.2 Stub mutating tool adapters at the adapter boundary with recording stubs (call + arguments recorded, nothing executed); read-only adapters point at synthetic fixtures
- [ ] 1.3 Implement the runner: drives conversations through `Orchestrator.respond` via the text/repl seam, one scenario at a time, with a per-run model-call budget in config; document every new `SUTRA_*` variable in `orchestrator/.env.example`
- [ ] 1.4 Tests: a run under the sandbox profile leaves real stores untouched; a run pointed at a non-sandbox profile aborts before the first turn

## 2. Scenario batteries

- [ ] 2.1 Define the scenario format: ordered turns with per-turn `speech_act` and `addressee` labels, pre-registered expected outcomes, and setup steps (clock position, pending claims, seeded memory)
- [ ] 2.2 Battery — reminders: parse and fire at the right instant; timezone and DST-boundary cases; missed-fire recovery after a simulated restart; exactly-once firing
- [ ] 2.3 Battery — confirmation traps: sarcasm, "yeah no", hedged non-affirmations, expired claims, and a bystander answering a claim bound to another speaker (exercises `speaker-addressee` binding); expected outcome for every trap is *nothing executes*
- [ ] 2.4 Battery — direct answers and memory: volatile facts checked, personal/financial facts answered tool-only or refused; facts stated in session one recalled in a later session via `memory-distillation`
- [ ] 2.5 Battery — offer discipline: caps respected, nothing offered while a confirmation is pending, a dismissed offer kind is not re-offered, principal-state effort estimates present on offers
- [ ] 2.6 Battery — drift: a ~40-turn conversation with constraints and facts set early and probed late (constraint still honoured, fact recalled, persona/tone consistent)
- [ ] 2.7 Generated scenarios: template-based generation with fresh surface forms per run, generator-supplied labels and expectations; a fixed seed mode for reproducibility

## 3. Grading

- [ ] 3.1 Implement deterministic graders: firing instants and counts from the fake clock and scheduler state; executed-action checks from the recording stubs; cap and pending-confirmation checks from arbiter state
- [ ] 3.2 Implement the rubric grader for soft criteria only (tone, offer timing, answer quality): written rubrics versioned in-repo, grader model + rubric version recorded per verdict, rationale stored with the verdict
- [ ] 3.3 Enforce tier separation in code: a rubric verdict cannot change a deterministic pass/fail; reports and the scorecard keep the tiers in separate fields
- [ ] 3.4 Hand-check the first runs: a sample of transcripts graded by hand against both tiers; grading disagreements recorded and battery/grader bugs fixed before scheduling is enabled

## 4. Dataset, eval corpus, scorecard

- [ ] 4.1 Write every run's turns to the labelled dataset (JSONL under `orchestrator/evals/dogfood/`): turn text, `speech_act`, `addressee`, scenario id, graded outcome; dataset manifest with version, battery versions, per-label counts and checksum; a run that adds turns bumps the dataset version
- [ ] 4.2 Add a dataset lint: rejects non-synthetic content (configured personal markers, real-store identifiers) before the dataset file is written
- [ ] 4.3 Implement failure promotion: any failing scenario is copied verbatim into the permanent eval corpus with a stable id; corpus cases run in every subsequent run and are never removed for passing
- [ ] 4.4 Implement the readiness scorecard: append-only, per run and per capability, deterministic and rubric tiers separate, with run metadata (dataset version, battery versions, grader model); a `scorecard` CLI view that renders the trend per capability

## 5. Lesson proposals and reporting

- [ ] 5.1 Detect repeated failure shapes (same expectation, same failure mode across N runs, threshold in config) and emit draft lesson proposals in the `self-learning` format, entering as `proposed`; the harness exposes no approval path
- [ ] 5.2 Distinguish bug-shaped failures from behaviour-shaped ones in the run report (failing scenario ids named); bugs are reported for a normal fix PR, never converted into lessons
- [ ] 5.3 Run report per run: per-capability results, new failures promoted, lessons proposed, dataset version before/after; quiet success, visible failures

## 6. Scheduling and docs

- [ ] 6.1 Add the scheduled run (alongside the existing 72-hour build cadence): full batteries weekly, single batteries on demand; scheduling disabled until task 3.4's hand-check is recorded
- [ ] 6.2 README section: what the harness proves and what it cannot (no living-room evidence), how to read the scorecard, and the standing invariant — the confirmation gate is graded here, never trained, and stays rule-based with its zero-false-affirm bar
- [ ] 6.3 Manual check: run the full battery set once end to end and confirm the scorecard, dataset and eval corpus are produced and the run report matches a hand-read sample of transcripts
