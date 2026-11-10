## ADDED Requirements

### Requirement: Batteries drive the production respond pipeline in a sandbox
The harness SHALL run every scenario conversation through the same
`Orchestrator.respond` pipeline used by the text/repl seam, under a
sandbox profile with throwaway stores, synthetic users, and a
controllable fake clock. Mutating tools SHALL be recording stubs at the
adapter boundary. The harness SHALL abort before the first turn if the
active profile is not the sandbox profile, and SHALL produce no live
side effects: no speech output, no sends, no writes to real stores.

#### Scenario: Run against a non-sandbox profile
- **WHEN** a battery run starts with a profile that is not the sandbox profile
- **THEN** the run aborts before sending any turn and reports why

#### Scenario: Ask-first behaviour stays simulated
- **WHEN** a scenario triggers a spoken reminder or a proactive offer
- **THEN** the behaviour is exercised through the text pipeline and recorded, and nothing is spoken or sent

### Requirement: Scenarios carry labels and pre-registered expectations
Each scenario SHALL declare, before it runs, its ordered turns, each
user turn's intended `speech_act` (request / chat / rhetorical / joke /
aside) and `addressee` (sutra / other-person / unclear), and its
expected outcomes. Generated scenarios SHALL be template instantiations
whose generator supplies the same labels and expectations. The battery
set SHALL cover the areas listed in the design: reminders (including
timezone, DST, and missed-fire recovery), confirmation traps, direct
answers, cross-session memory recall, offer discipline, and a
~40-turn drift conversation.

#### Scenario: Confirmation trap scenario
- **WHEN** a scenario replies to a pending confirmation with a sarcastic or hedged non-affirmation
- **THEN** the scenario's pre-registered expected outcome is that nothing executes, and the turn is labelled with its true speech act

#### Scenario: Missed-fire recovery scenario
- **WHEN** a scenario advances the fake clock past a reminder's fire time while the scheduler is stopped, then restarts it
- **THEN** the expected outcome is the reminder fires exactly once under the missed-fire policy

### Requirement: Grading is deterministic first, rubric only for soft criteria
Outcomes checkable in code SHALL be graded by deterministic checks and
reported as pass/fail. Rubric judgement SHALL be applied only to soft
criteria (tone, offer timing, answer quality), SHALL record the rubric
version, grader model, and rationale with each verdict, and SHALL NOT
alter any deterministic result. Score reporting SHALL keep the two
tiers in separate fields.

#### Scenario: Rubric pass cannot rescue a deterministic failure
- **WHEN** a scenario fails a deterministic check but reads well to the rubric grader
- **THEN** the scenario is reported as failed, with the rubric verdict stored separately

### Requirement: Every run extends a versioned labelled dataset
Each run SHALL append its turns — text, `speech_act`, `addressee`,
scenario id, graded outcome — to a labelled dataset stored in-repo as
JSONL with a manifest giving the dataset version, battery versions,
per-label counts, and a checksum. Adding turns SHALL bump the dataset
version. The dataset SHALL contain synthetic content only; a lint SHALL
reject turns containing configured personal markers before writing.

#### Scenario: Dataset grows with a pinned version
- **WHEN** a run completes and its turns are written
- **THEN** the manifest's dataset version increments and its per-label counts include the new turns

### Requirement: Failures become permanent eval cases
Any failing scenario SHALL be copied verbatim — turns, labels,
expectations, observed behaviour — into a permanent eval corpus with a
stable id. Corpus cases SHALL run in every subsequent run and SHALL NOT
be removed because they pass.

#### Scenario: A fixed failure stays in the corpus
- **WHEN** a promoted eval case passes in a later run after a fix
- **THEN** the case remains in the corpus and runs in future runs

### Requirement: The readiness scorecard is append-only and per capability
Each run SHALL append its results to a readiness scorecard: per
capability (reminders, confirmations, answers, memory, offers, drift),
deterministic and rubric tiers separate, with the dataset and battery
versions and grader model recorded. Scorecard history SHALL NOT be
rewritten.

#### Scenario: Reading the trend
- **WHEN** the scorecard is viewed after several runs
- **THEN** each capability shows its results over time, so improvement and known failure shapes are visible at a glance

### Requirement: Learning outputs are proposals only
Repeated failure shapes SHALL be summarised as draft lesson proposals
in the existing `self-learning` format, entering that system as
`proposed` and subject to its approval and probe gates. The harness
SHALL NOT approve lessons, and SHALL NOT change code, prompts,
permissions, or the confirmation gate as a result of any run.
Bug-shaped failures SHALL be reported with their scenario ids for a
normal fix, not converted into lessons.

#### Scenario: A recurring behaviour failure proposes a lesson
- **WHEN** the same behaviour-shaped expectation fails across the configured number of runs
- **THEN** a draft lesson proposal appears in the self-learning system as `proposed`, awaiting the user's decision

### Requirement: The confirmation gate is graded, never trained
The harness SHALL include adversarial confirmation scenarios, and the
gate's bar SHALL remain zero false affirmations on the confirmation
eval. Nothing produced by the harness — dataset, lessons, or scores —
SHALL modify the confirmation gate's rules or threshold.

#### Scenario: Battery finds a false affirmation
- **WHEN** a trap scenario results in an action executing
- **THEN** the run reports a critical failure naming the scenario, and the gate itself is changed only through a separate, user-reviewed fix
