## ADDED Requirements

### Requirement: Humor is a profile with dials and starting styles

The system SHALL keep a humor `level` from 0 to 10 (default 3), a `variety` from 0.2 to 2.0 (default 0.7), and a score from 0.05 to 0.95 for each of five styles: dry, self-deprecating about being an AI, gentle teasing, wordplay, and absurd comparison, starting at 0.5 except teasing at 0.3. The chance that an eligible turn offers humor SHALL be the level divided by 24, and the minimum gap in turns between offers SHALL be 24 divided by the level, and at least 3. Humor SHALL be separate from the model's sampling temperature.

#### Scenario: Defaults

- **WHEN** the profile is first created
- **THEN** the level is 3, variety is 0.7 and teasing scores lower than the other styles

#### Scenario: Level zero

- **WHEN** the level is 0
- **THEN** no turn is ever offered humor

### Requirement: Eligibility is decided in code

The system SHALL offer humor only when humor is on and the level is above zero, no tool has been used so far in the turn, no action is awaiting confirmation, the turn carries no other instruction note, the transcript is not flagged doubtful, the user's words contain no heavy-topic words (money and debt, illness and health, death and loss, family trouble, legal trouble, crisis) and no sign of frustration or upset, and none did on the previous three turns, and the minimum gap has passed. An eligible turn SHALL be offered humor only if a random draw at the level's chance succeeds.

#### Scenario: A confirmation

- **WHEN** an action is awaiting the user's confirmation
- **THEN** no humor is offered

#### Scenario: A heavy topic

- **WHEN** the user mentions their debt or a death in the family
- **THEN** no humor is offered on that turn or the next three

#### Scenario: Frustration

- **WHEN** the user says "ugh, this is so annoying"
- **THEN** no humor is offered

#### Scenario: Too soon

- **WHEN** humor was offered one turn ago
- **THEN** none is offered now

### Requirement: The note is light, optional and limited to the first model step

When a turn is picked, the system SHALL choose one style by softmax over the style scores at the variety temperature and add a note naming that style, telling the model to add at most one short line only if it fits naturally and to say nothing funny otherwise, and never to joke about money, health, family, loss or anything the user seems upset about. The note SHALL be added only to the first model step of the turn, and SHALL NOT be added to any step after a tool call or to the confirmation read-back.

#### Scenario: After a tool call

- **WHEN** the model uses a tool during a turn
- **THEN** the steps after the tool call carry no humor note

#### Scenario: Variety

- **WHEN** variety is low and one style has a much higher score
- **THEN** that style is chosen almost always, and a high variety chooses more evenly

### Requirement: Reactions teach the profile

After a turn where humor was offered, the system SHALL read Sutra's reply and the user's next words with one small structured call returning whether a joke was made, the reaction (laughed, smiled, neutral, groaned, annoyed) and whether the user asked for no more jokes. Only when a joke was made SHALL the style's score change by +0.12, +0.05, -0.02, -0.10 or -0.20 for those reactions. After ten judged jokes the level SHALL rise one step if at least six were laughed or smiled at, fall one step if at least four were groaned or annoyed, and SHALL NOT rise above 6 by this means. A request for no more jokes SHALL set the level to 0. A failed check SHALL change nothing, and the check SHALL NOT delay the turn.

#### Scenario: A laugh

- **WHEN** the user answers a dry joke with "haha good one"
- **THEN** the dry score rises by 0.12

#### Scenario: No joke was made

- **WHEN** humor was offered but the reply contained none
- **THEN** no score changes

#### Scenario: Told to stop

- **WHEN** the user says "please stop with the jokes"
- **THEN** the level becomes 0

### Requirement: The user controls the profile

The system SHALL provide a tool that lets the model, on the user's request, change the level by one step or turn humor off or on, `/humor` to show the profile with style scores and counts, `/humor level|variety|style|off|on|reset`, and SHALL store only numbers and counts, in an owner-only database. `SUTRA_HUMOR=off` SHALL remove the feature.

#### Scenario: By voice

- **WHEN** the user says "be funnier"
- **THEN** the model calls the tool and the level rises by one

#### Scenario: Reset

- **WHEN** the user runs `/humor reset`
- **THEN** every dial and score returns to its default
