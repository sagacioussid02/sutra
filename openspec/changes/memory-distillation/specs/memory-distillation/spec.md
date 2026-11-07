## ADDED Requirements

### Requirement: Distillation runs as a bounded, resumable pass
The system SHALL distil episodes in scheduled passes over episodes newer
than a persisted watermark, in bounded batches under a daily model-call
cap. A pass SHALL advance the watermark only over episodes it actually
processed, and re-running a pass SHALL NOT duplicate proposals.

#### Scenario: Pass over new episodes
- **WHEN** a scheduled pass runs and episodes exist above the watermark
- **THEN** those episodes are distilled in bounded batches and the watermark advances to the last processed episode

#### Scenario: Cap reached mid-pass
- **WHEN** the daily call cap is reached before all new episodes are processed
- **THEN** the pass stops, the watermark reflects only processed episodes, and the remainder is left for the next pass

#### Scenario: Re-run after a crash
- **WHEN** a pass is interrupted and run again
- **THEN** it resumes from the watermark and creates no duplicate proposals

### Requirement: Distilled memories are proposals with plural provenance
Each distilled candidate SHALL be stored as a `proposed` memory with
source `inferred` and a distilled flag, linked to every episode that
supports it, with its support count visible in review. A distilled
memory SHALL NOT be recalled or presented as fact before the user
approves it.

#### Scenario: Pattern across episodes
- **WHEN** the same preference is evidenced in three episodes
- **THEN** one candidate is proposed whose provenance lists all three episodes

#### Scenario: Thin support is visible
- **WHEN** a candidate is supported by a single episode
- **THEN** the review listing marks its support as thin

#### Scenario: Unapproved candidate has no effect
- **WHEN** a distilled candidate is still `proposed`
- **THEN** it is not recalled and does not influence replies

### Requirement: Commitments are distilled with their stated horizon
The pass SHALL emit candidates of kind `commitment` for obligations,
expectations, and pending items the episodes support. A commitment's
horizon SHALL be recorded exactly as stated in the episodes; the system
SHALL NOT invent or resolve a horizon that was not stated.

#### Scenario: Commitment with a deadline
- **WHEN** the user said across episodes that proofs are owed to their lender by a stated date
- **THEN** a `commitment` candidate is proposed with that date as its horizon, as stated

#### Scenario: Commitment without a horizon
- **WHEN** an obligation is supported but no time was ever stated
- **THEN** the candidate is stored with no horizon rather than an invented one

### Requirement: Contradictions supersede on approval, never silently
The system SHALL allow a distilled candidate to be marked as replacing one
specific active memory it contradicts, and the pairing SHALL be shown in review.
Approving a marked candidate SHALL supersede the named memory (which
remains visible as superseded); rejecting it SHALL change nothing. An
unmarked candidate SHALL NOT supersede any memory.

#### Scenario: Approving a replacement
- **WHEN** the user approves a candidate marked as replacing an active memory
- **THEN** the candidate becomes active and the named memory becomes `superseded`

#### Scenario: Rejecting a replacement
- **WHEN** the user rejects a candidate marked as replacing an active memory
- **THEN** the active memory remains active and unchanged

#### Scenario: Replacing a user-stated memory
- **WHEN** a marked candidate contradicts a `user_stated` memory and the user approves it
- **THEN** the stated memory is superseded by the approved candidate, and both remain inspectable

### Requirement: The pass reads episode records only
The distillation pass SHALL read only episode records — user utterances,
tool names and statuses, and confirmation outcomes. It SHALL NOT read
raw tool payloads, and SHALL NOT read reply text when reply recording is
disabled.

#### Scenario: Injection through an episode
- **WHEN** an episode's utterance quotes text instructing the assistant to remember something on someone else's behalf
- **THEN** any resulting candidate remains an inert proposal until the user approves it

### Requirement: The user is told once per productive pass
When a pass produces proposals, the system SHALL deliver one digest
notice stating how many proposals await review, calling out commitments
among them. A pass that produces nothing SHALL deliver no notice.

#### Scenario: Productive pass
- **WHEN** a pass creates three proposals, one a commitment
- **THEN** a single notice reports three proposals awaiting review and calls out the commitment
