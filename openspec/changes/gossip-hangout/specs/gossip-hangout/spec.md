## ADDED Requirements

### Requirement: A hangout mode entered and left by explicit phrase

The system SHALL enter a hangout mode only on an explicit start phrase and only when the group app is configured and answers, SHALL leave it on an explicit stop phrase or when the session ends, SHALL NOT start it during a held action, and SHALL end an interpreter session when it starts (and the reverse).

#### Scenario: Entering

- **WHEN** the user says "let's catch up with the group" and the app answers
- **THEN** Sutra says the group are fictional friends in a separate app, that messages go to that app, and that its info bot may look up public facts online

#### Scenario: Not configured or not answering

- **WHEN** the group app is not configured or does not answer
- **THEN** Sutra says it cannot reach the group and stays out of the mode

#### Scenario: Leaving

- **WHEN** the user says "leave the group"
- **THEN** the mode ends and the next message is answered by Sutra

### Requirement: The user's own words go through, and only those

While in the mode the system SHALL send each message to the group exactly as the user said it, SHALL NOT compose, summarize or rewrite anything for the group, and SHALL give the model no tool that reaches the group. A message matching heavy-topic or upset wording SHALL NOT be sent, and Sutra SHALL say it will keep that out of the group. A vent or crisis phrase SHALL end the mode and be handled by listening mode.

#### Scenario: Verbatim

- **WHEN** the user says "I think Tina and Vijay are getting married"
- **THEN** exactly that text is sent to the group

#### Scenario: A private matter

- **WHEN** the user mentions their debt in the mode
- **THEN** it is not sent and Sutra says so

#### Scenario: Distress

- **WHEN** the user says they want to end their life
- **THEN** the mode ends and the reply is the caring one

### Requirement: Replies carry the speaker and the persona's voice

The system SHALL return the group's replies as lines labelled with the speaker, and the voice client SHALL speak each line in the persona's voice (configurable), or prefix the name when the speaker has no voices. Speak-over SHALL work per line.

#### Scenario: Three friends reply

- **WHEN** Priya, Rahul and Ananya each reply
- **THEN** each line shows the speaker's name and is spoken in that persona's voice

### Requirement: The group is kept apart from what Sutra knows

A hangout turn SHALL NOT be added to conversation history, memory, the conversation graph or the people-and-plans extraction, SHALL carry no humor note and no unprompted offer, and the group's lines SHALL NOT enter the model's context.

#### Scenario: After leaving

- **WHEN** the user leaves the group and asks Sutra what Priya said
- **THEN** Sutra has no record of it

### Requirement: The user sees and controls it

The system SHALL provide `/hangout` showing the configured address and whether it answers, and `/hangout reset` to reset the group's world, and SHALL make no request when no address is configured.

#### Scenario: Reset

- **WHEN** the user runs `/hangout reset`
- **THEN** the group app's reset endpoint is called
