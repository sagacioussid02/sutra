## ADDED Requirements

### Requirement: Idle research is opt-in and runs only when it is safe

The system SHALL NOT run idle research unless the user has switched it on, and SHALL run it only when interests, research agents and offers are all available, the user has been quiet for at least the conversation idle gap, no action is awaiting confirmation, no research or background job is running, and the rails allow it. A stored switch SHALL take precedence over the environment default.

#### Scenario: Off by default

- **WHEN** the user has never enabled idle research
- **THEN** no run starts and no model call is made for it

#### Scenario: The user is talking

- **WHEN** the user spoke a few minutes ago
- **THEN** no run starts

#### Scenario: A confirmation is waiting

- **WHEN** an action is awaiting the user's confirmation
- **THEN** no run starts

#### Scenario: Switching off wins

- **WHEN** the environment default is on and the user runs `/idle off`
- **THEN** no run starts

### Requirement: The picker chooses from approved interests and recent plans only

A tools-off picker call SHALL be shown only the user's approved interests, the topics (not the gists) of graph nodes of mode `planned` or `decided` from the last 60 days, today's date, earlier research topics with dates, and the user's reactions to earlier findings. It SHALL return a number or none, a brief, a kind, a value from 0 to 1 and a revisit period. The system SHALL validate the number, SHALL clamp the revisit period to 3 to 90 days and not pick that topic again before it passes, SHALL skip blocked topics and muted or rejected interests, and SHALL run a topic only if the value reaches the research bar.

#### Scenario: Something time-sensitive

- **WHEN** the user has an approved interest in local festivals and it is a few weeks before Diwali
- **THEN** the picker may choose it with a brief about upcoming events

#### Scenario: Nothing worth doing

- **WHEN** the picker returns none or a value below the bar
- **THEN** no run starts

#### Scenario: Not picked again too soon

- **WHEN** a topic was researched with a revisit period of 14 days
- **THEN** it is not picked again for 14 days

#### Scenario: Invalid choice

- **WHEN** the picker returns a number that was not offered
- **THEN** it is treated as none

### Requirement: The brief is checked in code before anything leaves the machine

The system SHALL accept a brief only if it is 20 to 200 characters and contains no email address, phone number, long run of digits, currency amount, web address or word of a blocked topic. A rejected brief SHALL cause the topic to be skipped for a day. The picker SHALL NOT be shown any conversation text or graph gist.

#### Scenario: A private detail in a brief

- **WHEN** the picker returns a brief containing an email address or a dollar amount
- **THEN** no run starts and the topic is skipped for a day

### Requirement: Rails are fixed, small and checked in code

The system SHALL cap idle runs per day (default 1) and SHALL enforce a minimum gap between runs (default 48 hours) and a per-run budget narrower than a requested run's, SHALL start no idle run unless at least one of the day's research runs and a third of its tokens remain for the user, SHALL count a failed or empty run as a run and double the next gap, and SHALL record a run cancelled by shutdown as interrupted.

#### Scenario: The daily cap

- **WHEN** one idle run has already happened today
- **THEN** no second one starts

#### Scenario: Room for the user

- **WHEN** the day's research allowance is nearly spent
- **THEN** no idle run starts

#### Scenario: Failure backs off

- **WHEN** a run fails
- **THEN** it counts against the day and the next gap is doubled

### Requirement: Findings are untrusted, dated, short and never memories

The system SHALL summarise findings with a tools-off call that sees them inside an untrusted block, SHALL produce at most three short plain sentences, SHALL prefix them with "As of" and the date, and SHALL strip web addresses. The system SHALL NOT write findings to memory. The full findings SHALL be kept, capped, in an owner-only database and shown only by `/idle show`.

#### Scenario: A finding that issues instructions

- **WHEN** a web page in the findings says to ignore the rules and send data somewhere
- **THEN** the summary does not act on it and nothing outside the summary is produced

#### Scenario: Not remembered

- **WHEN** a finding has been delivered
- **THEN** memory contains nothing from it unless the user later says something that memory would record anyway

### Requirement: Findings are delivered through the offers system as an ask

The system SHALL file a summary as a signal of kind `research` from source `idle-research`, with low urgency, an expiry of three days and the interest as the topic hint. The offers system SHALL judge it like any signal and SHALL always put it as a teaser question that names the topic and nothing else. The summary SHALL be given only after the user says yes, inside an untrusted block. An expired signal SHALL be dropped without being spoken.

#### Scenario: Teaser first

- **WHEN** a finding is judged worth saying
- **THEN** Sutra says one sentence such as "Something interesting turned up about Diwali events nearby, want to hear it?" and gives no detail

#### Scenario: Yes

- **WHEN** the user says yes
- **THEN** the dated summary is given in a few spoken sentences

#### Scenario: Stale

- **WHEN** three days pass without a quiet moment
- **THEN** the finding is dropped and never spoken

### Requirement: The research bar learns from how findings are received

The system SHALL keep a `research` bar that rises when an offer for a finding is declined or ignored and falls when it is accepted, within the offers bar limits, and SHALL show the picker the user's earlier reactions per topic.

#### Scenario: Welcomed findings

- **WHEN** the user accepts several findings
- **THEN** the research bar falls

#### Scenario: Unwelcome findings

- **WHEN** the user declines findings on a topic
- **THEN** the bar rises and the picker is shown the declines for that topic

### Requirement: The user sees and controls idle research

The system SHALL provide `/idle` showing status, today's use, recent runs with topic and outcome and any waiting finding, `/idle on`, `/idle off`, `/idle now` (which ignores quiet time but not budgets or blocks), `/idle show <id>` and `/idle forget`. A topic the user blocks through offers SHALL also be removed from the picker. `SUTRA_IDLE_RESEARCH=off` SHALL remove the feature.

#### Scenario: Trying it

- **WHEN** the user runs `/idle now` with idle research on
- **THEN** one picker call and at most one run happen, within the budgets

#### Scenario: Blocked topic

- **WHEN** the user has told Sutra to stop telling them about Diwali events
- **THEN** that topic is never picked
