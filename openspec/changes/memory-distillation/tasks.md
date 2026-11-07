## 1. Pass machinery

- [x] 1.1 Add the distillation watermark to the memory database (schema version bump): last episode id processed, last run time, last run outcome
- [x] 1.2 Implement the pass runner: read hot episodes above the watermark in bounded batches, per user database; advance the watermark only over episodes actually processed
- [x] 1.3 Add the schedule (idle window, daily model-call cap in the `idle-research` style) and the `SUTRA_DISTILL` switch; a crashed or capped pass resumes from the watermark without duplicates
- [x] 1.4 Tests: watermark advances only on processed episodes; re-running a pass emits no duplicate proposals; the cap stops the pass and the remainder is next pass's input

## 2. Candidate generation

- [x] 2.1 Define the candidate schema (statement, kind including `commitment`, horizon as stated, supporting episode ids, support count) with a forced-schema model call, tools off
- [x] 2.2 Write the pass prompt: distil only what episodes support; state horizons exactly as given and never invent a date; skip the transient; include prior rejections for the same episodes and forbid re-emitting equivalents
- [x] 2.3 Feed the pass episode records only — utterances, tool names and statuses, confirmation outcomes — and nothing else; verify by test that no tool payload or (when recording is off) reply text reaches the call
- [x] 2.4 Tests: a preference shown across three episodes yields one candidate with three provenance links; a single mention is flagged thin; a stated deadline appears verbatim as the horizon

## 3. Proposals and supersession

- [x] 3.1 Store candidates as `proposed` / `inferred` memories with the distilled flag and plural provenance, in the existing review flow
- [x] 3.2 Implement replace-marking: a candidate may name one active memory it contradicts; the review listing shows the pair and the old memory's source
- [x] 3.3 On approval of a replace-marked candidate, supersede the named memory (kept, listed as superseded); on rejection, change nothing
- [x] 3.4 Extend `/why` to show every supporting episode of a distilled memory
- [x] 3.5 Tests: an approved distilled candidate supersedes a contradicted `user_stated` memory; a rejected one leaves it active; an unmarked candidate never supersedes; distilled proposals are never recalled before approval

## 4. Digest and control

- [x] 4.1 Emit one digest notice per pass that produced proposals: count awaiting review, commitments called out first; no notice for an empty pass
- [x] 4.2 Add `/distill` (run now; show last pass time, watermark, and outcome) and show distilled proposals distinctly in `/proposals`
- [x] 4.3 Tests: digest emitted once per productive pass and never per item; `/proposals` shows the distilled flag, support count, and any replace-pairing

## 5. Docs and verification

- [x] 5.1 Document every new `SUTRA_*` variable in `orchestrator/.env.example`; README section covering what the pass reads, what it never reads, and the approval rule
- [x] 5.2 Manual check with the real model on made-up conversations (not the user's real history, which would be sent to the model): the commitment, preference, replacement and ignored-injection cases behaved as specified
