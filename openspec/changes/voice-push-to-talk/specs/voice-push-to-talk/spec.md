## ADDED Requirements

### Requirement: A spoken turn produces a spoken reply
The system SHALL record one utterance from the microphone on a push-to-talk
signal, transcribe it, pass the transcript to the orchestrator's single turn
operation, and speak the reply aloud.

#### Scenario: A spoken question answered by a read-only tool
- **WHEN** the user records "what projects does minions manage" and ends the recording
- **THEN** the transcript is passed to the orchestrator
- **AND** the reply is spoken aloud and also printed

#### Scenario: An empty recording
- **WHEN** the user ends a recording that contains no speech
- **THEN** no turn is sent to the orchestrator
- **AND** the user is told nothing was heard

#### Scenario: Quitting
- **WHEN** the user gives the quit signal
- **THEN** the session closes cleanly and releases the microphone

### Requirement: Speech engines are replaceable
The system SHALL reach speech-to-text and text-to-speech only through
`Transcriber` and `Speaker` interfaces, so an engine can be replaced without
changing the voice loop.

#### Scenario: Running with scripted engines
- **WHEN** the voice loop runs with a scripted transcriber and speaker
- **THEN** it completes turns without a microphone, speakers, or network

### Requirement: Doubtful transcripts never confirm an action
While a `confirm-first` action is pending, the system SHALL NOT pass a
transcript to the orchestrator if it is empty or its confidence is below the
configured threshold. It SHALL re-ask instead, and the pending action SHALL
remain held.

#### Scenario: Low-confidence reply to a confirmation
- **WHEN** an action is pending and the reply transcript is below the confidence threshold
- **THEN** the orchestrator is not called with that transcript
- **AND** the user is asked to repeat their answer
- **AND** the action has not run

#### Scenario: Clear yes
- **WHEN** an action is pending and the user clearly says "yes"
- **THEN** the transcript is passed to the orchestrator and the action runs only through the existing affirm path

#### Scenario: Repeated doubtful replies
- **WHEN** the user's replies stay below the threshold up to the re-ask limit
- **THEN** the pending action is dropped and the user is told nothing was done

### Requirement: What was heard is shown
The system SHALL print every transcript, and SHALL speak back the transcript
of a reply to a pending confirmation before acting on it.

#### Scenario: Confirmation readback
- **WHEN** the user answers a pending confirmation by voice
- **THEN** the system states what it heard before the action runs or is dropped

### Requirement: Re-asks are phrased for speech
The system SHALL NOT read the gateway's raw action description aloud when
re-asking after an unclear reply to a confirmation.

#### Scenario: Unclear spoken reply
- **WHEN** an action is pending and the user's reply is classified unclear
- **THEN** the spoken re-ask is a short yes-or-no question without the raw description

### Requirement: Audio is not kept by default
The system SHALL hold recorded audio only for the duration of the turn unless
the user enables recording to a directory.

#### Scenario: Default behavior
- **WHEN** a turn completes with default settings
- **THEN** no audio file has been written

### Requirement: Microphone failures are explicit
The system SHALL report a clear error when the microphone cannot be opened,
and when a recording contains only silence, which is how macOS presents denied
permission.

#### Scenario: Microphone cannot be opened at start
- **WHEN** the microphone cannot be opened at startup
- **THEN** the system reports that microphone access is needed and does not start a session

#### Scenario: A recording of pure silence
- **WHEN** a recording contains only silence
- **THEN** the system reports a possible microphone permission problem and sends no turn

### Requirement: Private mode keeps speech local
The system SHALL offer a private mode in which speech-to-text and
text-to-speech run locally and no audio or spoken text is sent to a cloud
speech service, switchable during a session and selectable at start.

#### Scenario: Switching to private mid-session
- **WHEN** the user switches to private mode
- **THEN** later turns are transcribed and spoken by the local engines only

#### Scenario: No cloud key configured
- **WHEN** no cloud speech key is configured
- **THEN** the system starts in private mode and says so

### Requirement: The assistant speaks as a named person, not a robot
The system SHALL give the assistant a configurable name and a conversational
persona that uses natural fillers sparingly, while keeping every honesty and
confirmation rule in force.

#### Scenario: Persona applied
- **WHEN** voice runs
- **THEN** the persona instructions, containing the configured name, are part of the system prompt alongside the existing rules

#### Scenario: A slow reply
- **WHEN** a reply takes longer than the filler delay
- **THEN** a short spoken filler is played before the reply, and the two never overlap

#### Scenario: A fast reply
- **WHEN** a reply arrives before the filler delay
- **THEN** no filler is spoken

### Requirement: The turn ends when the user stops speaking
The system SHALL end a recording when the user has been quiet for a configurable
time after speaking, without any key press, and SHALL give up if the user never
starts speaking.

#### Scenario: Finishing a sentence
- **WHEN** the user speaks and then is quiet for the configured time
- **THEN** the recording ends and the turn proceeds

#### Scenario: A short pause
- **WHEN** the user pauses for less than the configured time and continues
- **THEN** the pause does not end the turn

#### Scenario: Nobody speaks
- **WHEN** no speech is detected within the no-speech timeout
- **THEN** no turn is sent and the session returns to idle

### Requirement: Conversation continues hands-free
While conversation mode is on, the system SHALL listen again after speaking a
reply, and SHALL return to idle when the user stays quiet.

#### Scenario: A follow-up sentence
- **WHEN** the assistant has finished speaking and the user speaks again
- **THEN** the new utterance is handled as the next turn without a key press
