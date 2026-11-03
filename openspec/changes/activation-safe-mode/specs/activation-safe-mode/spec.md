## ADDED Requirements

### Requirement: Three modes, saved, consulted by everything

The system SHALL hold one mode, `full`, `limited` or `off`, saved in an owner-only file, SHALL use the saved mode in preference to the configured starting mode, and SHALL treat an unreadable file as `limited`.

#### Scenario: A restart does not raise it

- **WHEN** the mode was lowered to limited and Sutra is restarted
- **THEN** it starts in limited

#### Scenario: A damaged file

- **WHEN** the saved mode cannot be read
- **THEN** the mode is limited

### Requirement: Limited mode allows only looking things up

In `limited` mode the system SHALL offer and run only gateway tools whose name, after the project prefix, begins with get, list, read, show, find, search, describe, view, status or check, plus tools named in `SUTRA_LIMITED_TOOLS`, and local tools that only reduce behaviour or read; SHALL block the research tool and any gateway tool it does not recognize as reading; and SHALL refuse a blocked tool the model asks for anyway.

#### Scenario: A read

- **WHEN** the user asks for their debts in limited mode
- **THEN** the debts tool is available and runs

#### Scenario: A change

- **WHEN** the user asks to create a goal in limited mode
- **THEN** the create tool is not offered, and if the model asks for it the call is refused

#### Scenario: A name the rule has not seen

- **WHEN** a tool is named by an unfamiliar verb
- **THEN** it is blocked unless listed in `SUTRA_LIMITED_TOOLS`

### Requirement: Limited mode is quiet and spends nothing

In `limited` and `off` mode the system SHALL make no unprompted offer, check-in, question, heads-up or suggestion, SHALL start no idle research run, SHALL make no feed requests, and SHALL not open the group chat.

#### Scenario: A ready heads-up

- **WHEN** a weather signal is ready and the mode is limited
- **THEN** it is not said

#### Scenario: Idle research

- **WHEN** the mode is limited
- **THEN** idle research does not run

### Requirement: Lowering the mode cancels what is waiting

When the mode drops below `full` the system SHALL drop any action awaiting confirmation, SHALL refuse to confirm one afterwards, and SHALL say in one line that nothing was done.

#### Scenario: A held action

- **WHEN** an action awaits confirmation and the user says "safe mode"
- **THEN** the action is dropped and a later "yes" does nothing

### Requirement: The voice can only lower the mode

The system SHALL lower the mode on a spoken keyword matched as a whole short utterance in English or Hindi, regardless of transcript confidence, and SHALL NOT raise it in response to anything spoken. Raising SHALL require the typed `/mode` command or a key in the voice client.

#### Scenario: A keyword

- **WHEN** the user says "go quiet"
- **THEN** the mode becomes off and Sutra says it is off and how to turn it back on

#### Scenario: Not inside a sentence

- **WHEN** the user says "I want to talk about the safe mode setting on my car"
- **THEN** the mode does not change

#### Scenario: Asking by voice to come back

- **WHEN** the mode is limited and the user says "full mode please"
- **THEN** the mode stays limited and Sutra says to use the keyboard

### Requirement: A silent distress phrase

When `SUTRA_DURESS_PHRASE` is set and the user's words contain it, the system SHALL lower the mode to `limited` without announcing it, SHALL drop any pending action, SHALL handle the rest of the utterance as an ordinary message in limited mode, and SHALL NOT log or show the phrase.

#### Scenario: Under pressure

- **WHEN** an action awaits confirmation and the user says the phrase inside a sentence
- **THEN** the mode is limited, the action is dropped, and nothing in the reply announces why

#### Scenario: The phrase is private

- **WHEN** the configuration is printed or logged
- **THEN** the phrase does not appear

### Requirement: Off means off

In `off` mode the system SHALL answer every message with one line saying it is off and how to turn it back on, and the voice client SHALL release the microphone, start no conversation, and respond only to the keyboard.

#### Scenario: Off in voice

- **WHEN** the mode becomes off
- **THEN** the microphone is released and only a key restores it

### Requirement: Wake word activation keeps audio local until it is heard

In `wake` activation the system SHALL transcribe each spoken segment with the local recognizer only, SHALL treat a segment as addressed to Sutra only if it contains a wake phrase (allowing for common mishearings), SHALL send audio to no cloud service before that, and SHALL handle the words after the wake phrase as the command. The button SHALL work at any time. If the local recognizer is unavailable the system SHALL say so and remain on the button.

#### Scenario: Not addressed

- **WHEN** the room is talking about something else
- **THEN** nothing is sent to the cloud and Sutra does not answer

#### Scenario: Wake and command together

- **WHEN** the user says "Hey Sutra, what time is it"
- **THEN** the command "what time is it" is handled

#### Scenario: Wake alone

- **WHEN** the user says only "Hey Sutra"
- **THEN** Sutra says "Yes?" and listens

### Requirement: First-person Hindi follows a chosen gender

The system SHALL add to the prompt a line setting the grammatical gender Sutra uses for itself in Hindi from `SUTRA_ASSISTANT_GENDER` (feminine by default).

#### Scenario: Default

- **WHEN** no setting is given
- **THEN** the prompt asks for feminine forms in Hindi
