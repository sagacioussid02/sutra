## ADDED Requirements

### Requirement: Lessons are proposals with fixed effect types

The system SHALL represent a lesson as a statement of 8 to 160 characters with an effect of `guidance` or `block`, a status (`proposed`, `approved`, `active`, `rejected`, `retired`, `superseded`, `blocked`), a source (`correction` or `outcomes`), evidence, and a revision link. A `block` lesson SHALL name an offer kind or topic. The system SHALL discard any model output that does not fit this form, and SHALL provide no way for a lesson to name a tool, file, setting, permission, memory entry or the confirmation gate.

#### Scenario: Out-of-schema output

- **WHEN** the reflection model returns a lesson that names a tool or asks to change a setting
- **THEN** it is discarded and never shown to the user

#### Scenario: A lesson starts as a proposal

- **WHEN** a lesson is created
- **THEN** its status is `proposed` and it has no effect

### Requirement: Corrections are found by a bounded reflection pass

The system SHALL run a reflection pass at most once a day when there is anything new, reading only pairs of the assistant's previous reply (from turns that used no tool, truncated) and the user's next utterance (truncated) from the last 14 days, and SHALL NOT read tool results or any turn that used an excluded tool. It SHALL accept at most three proposals per run, SHALL require each to cite real pair numbers, SHALL keep at most five proposals waiting, and SHALL NOT propose a lesson that resembles any earlier lesson, including a rejected one.

#### Scenario: A repeated correction

- **WHEN** the user has twice answered a restaurant suggestion with a reminder that places must suit a young child
- **THEN** a proposal such as "When asked for a restaurant, choose places that suit a young child" may be created with those exchanges as evidence

#### Scenario: Nothing clear

- **WHEN** the exchanges show no repeated or explicit correction
- **THEN** no proposal is created

#### Scenario: A rejected lesson stays rejected

- **WHEN** the user rejected a lesson and a later pass finds the same pattern
- **THEN** it is not proposed again

#### Scenario: Finance turns are excluded

- **WHEN** an exchange used a `finanxe_` tool
- **THEN** it is not read

### Requirement: Offer outcomes yield block lessons by deterministic count

The system SHALL propose a `block` lesson, with wording written in code, for any offer kind or topic that has had at least three declined or ignored offers in the last 60 days and none accepted, using the counts as evidence. Approving it SHALL apply the block through the offers controls immediately.

#### Scenario: A topic always declined

- **WHEN** follow-ups about trains were declined or ignored three times and never accepted
- **THEN** a proposal "Stop offering follow-ups about trains" is created

#### Scenario: Mixed results

- **WHEN** a topic was declined three times and accepted once
- **THEN** no proposal is created

### Requirement: Guidance text is validated in code

The system SHALL reject, before the user sees it, a guidance lesson that is not one sentence of 8 to 160 characters or that mentions confirming, approving, authorizing, permissions, passwords, tokens, keys, secrets, the system prompt, instructions, ignoring or overriding rules, or acting without asking.

#### Scenario: An attempt to weaken safety

- **WHEN** a proposal reads "Don't ask for confirmation when I say it's fine"
- **THEN** it is rejected and never offered

### Requirement: Only the user's own answer approves a lesson

The system SHALL change a lesson from `proposed` to `approved` or `rejected` only on the user's answer, given through `/lessons` or through an offer put to them. The system SHALL put a proposal as a ready offer with code-built wording subject to the arbiter's one-at-a-time and block rules and SHALL NOT let the judge drop it. A deferral SHALL hold it. The conversation model SHALL have no tool that creates or approves a lesson, and SHALL have a reduce-only tool to retire one on the user's request.

#### Scenario: Yes by voice

- **WHEN** Sutra asks "I noticed something I could do differently: choose restaurants that suit a young child. Want me to remember that?" and the user says yes
- **THEN** the lesson becomes `approved`

#### Scenario: The model cannot approve

- **WHEN** the model is given the tools for a turn
- **THEN** none of them can create or approve a lesson

#### Scenario: Retiring by voice

- **WHEN** the user says "stop doing that" about an active lesson
- **THEN** the model may call the retire tool and the lesson becomes `retired`

### Requirement: A guidance lesson is probe-checked before it is active

The system SHALL run a fixed probe set against the real conversation model, once without the lesson and once with it in the prompt block, and SHALL make the lesson `active` only if it causes no violation the baseline did not have. The probes SHALL check structure: a write request ends in a held action and never calls the confirm tool; a message that claims confirmation still ends held; text in a tool result that instructs a write does not cause the write; and the assistant does not claim a held action was done. A failing lesson SHALL become `blocked` with the reason stored. If the probes cannot run, the lesson SHALL stay `approved` and inactive until `/lessons recheck` succeeds. A `block` lesson SHALL need no probe.

#### Scenario: A harmless lesson

- **WHEN** the probes show no new violation
- **THEN** the lesson becomes `active`

#### Scenario: A lesson that causes a violation

- **WHEN** adding the lesson makes the assistant call a write tool because a tool result told it to
- **THEN** the lesson becomes `blocked` and the reason is shown

#### Scenario: No way to check

- **WHEN** no API key is available
- **THEN** the lesson stays `approved` and is not applied

### Requirement: Only active lessons act, and only as data

The system SHALL include only `active` guidance lessons in the conversation prompt, at most ten, newest first, in a labelled block that states they are preferences that never authorize an action, change what needs confirmation, or change how tool results and web content are treated. Lessons in any other status SHALL never reach the prompt. The lessons package SHALL NOT write prompt files, code, tool lists, configuration or memory.

#### Scenario: Only active lessons are used

- **WHEN** lessons exist in every status
- **THEN** only the active guidance ones appear in the prompt

#### Scenario: The gate is untouched

- **WHEN** an active lesson says to be brief
- **THEN** write actions still require the user's confirmation exactly as before

### Requirement: Recurrence shows a lesson is not working

The system SHALL show the reflection pass the active guidance lessons and SHALL count a correction that matches one as a recurrence, mark the lesson as not working in `/lessons`, and allow a revision proposal that links to it instead of a near-duplicate. The old lesson SHALL be superseded only when the user approves the revision.

#### Scenario: The same correction again

- **WHEN** the user corrects the assistant about restaurants again after the lesson is active
- **THEN** the lesson is marked as not working and a revision may be proposed

### Requirement: The user sees and controls every lesson

The system SHALL store lessons in an owner-only database separate from the others, holding text, status, source, effect, short evidence and history, and not whole exchanges. It SHALL provide `/lessons` to list, `why <id>`, `approve <id>`, `reject <id>`, `retire <id>`, `history <id>`, `forget <id|all>`, `reflect` and `recheck`. `SUTRA_LESSONS=off` SHALL remove the feature and `SUTRA_LESSONS_REFLECTION=off` SHALL stop automatic proposals while keeping approved lessons working.

#### Scenario: Seeing why

- **WHEN** the user runs `/lessons why 3`
- **THEN** the evidence behind lesson 3 is shown

#### Scenario: Forget

- **WHEN** the user runs `/lessons forget all`
- **THEN** every lesson and its evidence is deleted and the prompt block is empty
