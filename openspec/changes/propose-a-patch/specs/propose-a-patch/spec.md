## ADDED Requirements

### Requirement: Drafting starts only with the user's yes
The system SHALL offer to draft a missing capability when no tool or agent fits a request, and SHALL start a patch run only after the user agrees. A patch run SHALL be a background job that does not block the conversation.

#### Scenario: Nothing fits
- **WHEN** the user asks for something no tool or agent can do and patches are enabled
- **THEN** the assistant offers to draft a way to do it and starts nothing until the user says yes

#### Scenario: The user declines
- **WHEN** the user says no to the offer
- **THEN** no worktree is created and no model call is spent on drafting

#### Scenario: Switched off
- **WHEN** `SUTRA_PATCHES` is off
- **THEN** the `propose_capability` tool is not offered and `/patches` reports that patches are off

### Requirement: Drafts never touch the running code
The system SHALL create each draft in a fresh git worktree on a new branch `sutra/patch-<id>` cut from `main`, outside the running checkout. The system SHALL NOT merge, push, deploy, install, or otherwise apply a draft.

#### Scenario: Isolated worktree
- **WHEN** a patch run starts
- **THEN** all of its file changes are made in the new worktree and the running checkout is unchanged

#### Scenario: No self-application
- **WHEN** a draft finishes with passing tests
- **THEN** it remains on its branch unmerged and unapplied until the user merges it themselves

### Requirement: The safety layer cannot be drafted against
The system SHALL refuse any create, change, rename or delete of a protected path, and SHALL check the finished diff against the same list and reject the whole patch if any protected path appears. The protected paths SHALL include the confirmation gate, safety modes, adaptive authentication, the intent classifier, the orchestrator's tool-gate code, the gateway's authentication, tier, confirmation, audit and registry code, token and environment files, hooks, and this feature's own code. The list SHALL NOT be changeable by configuration or by the drafter.

#### Scenario: Write to a protected path
- **WHEN** the drafter tries to write a file under a protected path
- **THEN** the write is refused and the refusal is recorded

#### Scenario: Rename into protection
- **WHEN** the finished diff contains a rename or deletion touching a protected path
- **THEN** the whole patch is rejected and no proposal is presented as ready

#### Scenario: Path escape
- **WHEN** the drafter uses `..` or a symlink to reach a file outside the worktree
- **THEN** the access is refused

### Requirement: Generated code runs only under a sandbox
The system SHALL run a draft's tests only under an operating-system sandbox with no network access, writes limited to the worktree, a scrubbed environment and a time limit. Where no sandbox is available the system SHALL NOT run the tests, and SHALL mark the draft as drafted but not tested.

#### Scenario: Sandboxed test run
- **WHEN** the drafter runs the tests and a sandbox is available
- **THEN** the tests run with no network, no credentials in the environment, and a timeout

#### Scenario: No sandbox
- **WHEN** no supported sandbox is present
- **THEN** the tests are not run, and the proposal states that it is untested

### Requirement: Runs are bounded
The system SHALL enforce, in code, limits on tool calls, output tokens, wall-clock time and a daily number of runs, and SHALL end a run that reaches a limit with whatever it has, marked partial.

#### Scenario: Budget reached
- **WHEN** a run reaches its tool-call limit
- **THEN** it ends and its result is marked partial

#### Scenario: Daily cap
- **WHEN** the daily cap of runs has been reached
- **THEN** a new run is not started and the user is told why

### Requirement: Results are untrusted proposals
The system SHALL treat the drafter's summary and diff as untrusted. The announcement SHALL be composed with tools disabled, SHALL say that a draft exists and what it claims to do, and SHALL NOT apply it. The user SHALL be able to list, inspect and discard drafts.

#### Scenario: Injected instruction in a draft summary
- **WHEN** a draft's summary contains text telling the assistant to merge it or skip review
- **THEN** nothing is merged and the text is shown only as quoted data

#### Scenario: Reviewing a draft
- **WHEN** the user opens a draft with `/patches show <id>`
- **THEN** they see the summary, file list, test outcome and diff stat, and the branch name to review with git

#### Scenario: Discarding
- **WHEN** the user discards a draft
- **THEN** its worktree and branch are removed and it no longer appears in the list
