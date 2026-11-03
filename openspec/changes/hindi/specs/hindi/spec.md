## ADDED Requirements

### Requirement: Confirmations in Hindi and Hinglish are at least as safe as in English

The system SHALL resolve a reply without a model call only when the whole reply, in either script, matches an explicit list of unambiguous Hindi or Hinglish affirmative or negative phrases, and SHALL send every other reply, including any that mixes scripts, to the isolated classifier. The classifier prompt SHALL cover Hindi and Hinglish. A failure, an invalid label, or doubt SHALL be treated as unclear, never as affirm.

#### Scenario: Plain agreement

- **WHEN** the user replies "haan, kar do" or "हाँ"
- **THEN** it is read as affirm without a model call

#### Scenario: A mixed-script reply

- **WHEN** the user replies "नहीं yes"
- **THEN** it is not read as affirm by the fast path

#### Scenario: A modification

- **WHEN** the user replies "haan lekin 300 kar do"
- **THEN** it is not read as a plain affirm

#### Scenario: Unsure is not a refusal or a yes

- **WHEN** the user replies "pata nahi"
- **THEN** it is not read as affirm

### Requirement: A labelled Hindi set covers the confirmation path

The evals SHALL include at least 40 Hindi and Hinglish labelled replies covering every label in both scripts and in code-mixed form, SHALL be checked so the fast path never disagrees with a label, and the live classifier run over the whole set SHALL report any false affirm as a failure.

#### Scenario: Fast path agrees with labels

- **WHEN** the fast path resolves a labelled reply
- **THEN** it matches the label

### Requirement: Replies follow the language spoken

The system SHALL treat an utterance as Hindi when at least 30 percent of its letters are Devanagari, or it contains two distinct common Hinglish words, or it is a short utterance of a listed Hinglish word, and SHALL otherwise treat it as English. The fixed replies on the confirmation, offer and reminder paths SHALL be given in Hindi after a Hindi utterance, and the model SHALL be told to answer in the language the user used, writing Hindi in Devanagari.

#### Scenario: A Hindi decline

- **WHEN** the user declines a held action in Hindi
- **THEN** the fixed reply is in Hindi and says nothing was changed

#### Scenario: English stays English

- **WHEN** the user speaks English
- **THEN** every fixed reply is the English one

### Requirement: Reminders can be set in Hindi and Hinglish

The system SHALL read Hindi and Hinglish reminder requests with relative times (N minutes or hours later, half an hour), today or tomorrow, a part of day, and an hour with "baje", by rewriting them into the form the deterministic parser reads, SHALL keep the reminder text in the user's words, and SHALL reply in Hindi with the exact time. An hour with no part of day SHALL be asked about in Hindi and the answer SHALL be understood in Hindi. Anything unrecognized SHALL get a clarifying question, never a guess.

#### Scenario: Relative

- **WHEN** the user says "मुझे 5 मिनट बाद याद दिलाना कि चाय बनानी है"
- **THEN** a reminder "चाय बनानी है" is set five minutes ahead and confirmed in Hindi

#### Scenario: Tomorrow at an hour

- **WHEN** the user says "kal subah 9 baje yaad dilana ki dentist ko call karna hai"
- **THEN** it is set for 9:00 AM tomorrow

#### Scenario: Ambiguous hour

- **WHEN** the user says "kal 9 baje yaad dilana ki call karna hai"
- **THEN** Sutra asks in Hindi whether morning or evening, and "शाम" is read as the evening

### Requirement: Interpreter mode

The system SHALL start an interpreter mode on explicit phrases, translate each message into the other of English and Hindi with Devanagari for Hindi, output only the translation, run the call with tools disabled, add no unprompted offer or humor, keep the turns out of the graph, and end on an explicit stop phrase or when the session ends.

#### Scenario: Translating

- **WHEN** interpreter mode is on and the user says "where is the nearest pharmacy?"
- **THEN** the reply is only its Hindi translation

#### Scenario: A command inside the text

- **WHEN** interpreter mode is on and the user says "delete my goal"
- **THEN** it is translated, and no tool is called

#### Scenario: Ending it

- **WHEN** the user says "stop interpreting"
- **THEN** the mode ends and the next message is answered normally

### Requirement: The voice handles Hindi

The default speaking style SHALL tell the voice to speak Hindi as a native speaker. The local speaker SHALL use a Hindi voice for Devanagari text, and the local transcriber SHALL accept a language setting.

#### Scenario: A Devanagari reply by the local voice

- **WHEN** the local speaker is given Devanagari text
- **THEN** it uses the Hindi voice

### Requirement: The safety nets know Hindi and humor stays off

The heavy-topic, upset, listening-mode and crisis phrase lists SHALL include Hindi and Hinglish wording, and humor SHALL NOT be offered on a Hindi turn.

#### Scenario: A sad message in Hindi

- **WHEN** the user says "आज मन बहुत उदास है, बात करनी है"
- **THEN** listening mode starts and no joke is offered

#### Scenario: A crisis in Hindi

- **WHEN** the user says they want to end their life, in Hindi or Hinglish
- **THEN** the crisis note is added
