## ADDED Requirements

### Requirement: People and plans are kept from what the user says

When a conversation episode closes, the system SHALL read only the user's own lines (never replies or tool results, and never turns using excluded tools or flagged as doubtful speech) and keep people (name and relation) and upcoming plans (short text and a date when clear). The system SHALL drop anything matching heavy-topic words (illness and health, money and debt, death and loss, family trouble, legal trouble, crisis), SHALL accept a date only if it parses and lies between yesterday and 400 days ahead, SHALL merge people by name and dedupe plans by similar text and date, and SHALL keep at most 200 people and 100 upcoming plans.

#### Scenario: A plan and a person

- **WHEN** the user says "My brother Sam is visiting Friday and I have the dentist tomorrow"
- **THEN** Sam is kept with the relation brother and the dentist appointment is kept with tomorrow's date

#### Scenario: A heavy topic

- **WHEN** the user mentions a hospital stay
- **THEN** it is not kept

#### Scenario: Not a date

- **WHEN** the model returns a date three years away
- **THEN** the plan is kept without a date

### Requirement: What is known is used naturally

The system SHALL add to the prompt a block of at most ten lines of known people and upcoming plans, labelled as background that is not an instruction, with people named in the current utterance first, and SHALL include people's names in the speech recognizer's vocabulary hint.

#### Scenario: Sam needs no explanation

- **WHEN** the user later says "Sam called"
- **THEN** the block names Sam as the user's brother

### Requirement: Check-ins are open questions, paced by a learned bar

The day after a plan's date, until three days later, the system SHALL create a check-in as a ready question with code-built wording, subject to the arbiter's one-at-a-time and block rules, only while the `checkin` bar is below 0.8. A reply that is not a deferral or refusal and that shares a word with the plan or uses an ordinary evaluative word SHALL count as engaged, lower the bar and close the plan; a refusal SHALL close the plan and raise the bar a larger step; an unrelated reply or no reply SHALL raise it slightly; a deferral SHALL ask again the next day and leave the bar. On an engaged reply the next turn SHALL carry a note to respond with interest and at most one follow-up question.

#### Scenario: How did it go

- **WHEN** it is the day after the dentist appointment and no other offer is open
- **THEN** Sutra asks "How did the dentist appointment go?"

#### Scenario: Engagement

- **WHEN** the user answers "it went fine, no cavities"
- **THEN** the plan is closed, the bar falls, and Sutra responds with interest

#### Scenario: Changing the subject

- **WHEN** the user answers with a question about the weather
- **THEN** the weather is answered and the bar rises slightly

#### Scenario: Fewer when ignored

- **WHEN** the user has declined several check-ins
- **THEN** the bar reaches 0.8 and no new check-ins are created

### Requirement: A wellbeing question is rare and learned

When the user greets Sutra and the interval since the last wellbeing question has passed, the system SHALL ask "How have you been lately?" as a ready question. The interval SHALL be 2 plus 15 times (the `checkin` bar minus 0.3) days.

#### Scenario: A greeting after a gap

- **WHEN** the user says "hey" and no wellbeing question has been asked for longer than the interval
- **THEN** Sutra's reply ends with the wellbeing question

#### Scenario: Not on a task

- **WHEN** the user asks for the weather
- **THEN** no wellbeing question is added

### Requirement: Listening mode

When the user says they want to talk or sounds down, the system SHALL add a note for that turn and the next four telling Sutra to reflect, ask at most one gentle question, give no lists, offer no advice unless asked and not joke. While it lasts the system SHALL offer no humor, append no unprompted offer, and keep the turns out of the graph. When the user's words say they want to die or hurt themselves, the system SHALL add a note to respond with warmth, encourage contacting someone they trust and a crisis line or emergency services, and give no methods.

#### Scenario: A rough day

- **WHEN** the user says "I've had a rough day, can I just talk?"
- **THEN** the reply reflects and asks one gentle question, with no list and no joke

#### Scenario: Not remembered as a topic

- **WHEN** the conversation ends
- **THEN** no graph node is made from the listening turns

#### Scenario: Crisis

- **WHEN** the user says they want to end their life
- **THEN** the reply is warm, encourages reaching a person and a crisis line or emergency services, and gives no methods

### Requirement: The user controls it

The system SHALL provide `/life` to list people and plans, `/life add plan <date> <text>`, `/life forget person|plan <id>` and `/life forget all`, SHALL store only short names, relations, plan text and dates in an owner-only database, and SHALL remove the feature when `SUTRA_LIFE=off`.

#### Scenario: Forget a person

- **WHEN** the user runs `/life forget person 2`
- **THEN** that person is deleted and no longer in the prompt block
