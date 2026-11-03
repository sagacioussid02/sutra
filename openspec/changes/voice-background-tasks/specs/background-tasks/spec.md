## ADDED Requirements

### Requirement: The user can speak while a request is being processed
The system SHALL keep listening while a request is in flight, and SHALL handle
a new utterance immediately instead of waiting for the earlier request.

#### Scenario: Asking something else during a slow request
- **WHEN** a request is still being processed and the user asks a second question
- **THEN** the second question is answered without waiting for the first

#### Scenario: The earlier request keeps running
- **WHEN** the user speaks while a request is in flight
- **THEN** that request continues in the background and is not cancelled

### Requirement: Concurrent requests do not interfere
The system SHALL run each request in its own conversation lane so one request's
tool calls and history cannot corrupt another's.

#### Scenario: Two requests at once
- **WHEN** two requests run at the same time
- **THEN** each lane's history remains a valid sequence of tool calls and results

### Requirement: Waiting is announced
The system SHALL tell the user once, in natural speech, when a request is
taking a while and that they can ask something else, but only when it can in
fact listen.

#### Scenario: A slow tool call
- **WHEN** a request is still running after the wait-notice delay
- **THEN** Sutra says it is working on it and that the user can ask something else

#### Scenario: A fast request
- **WHEN** a request finishes before the wait-notice delay
- **THEN** no wait notice is spoken

### Requirement: Finished background work is announced only after asking
The system SHALL NOT speak the result of a background request unprompted. It
SHALL ask first and speak the result only after the user agrees.

#### Scenario: Result arrives while idle
- **WHEN** a background request finishes and the user is idle
- **THEN** Sutra asks whether the user wants it now
- **AND** speaks the result only after a clear yes

#### Scenario: Result arrives mid-conversation
- **WHEN** a background request finishes while the user is talking with Sutra
- **THEN** Sutra waits for a natural gap before asking

#### Scenario: The user says later
- **WHEN** the user declines or does not answer
- **THEN** the result stays queued and can be retrieved by asking what came back

### Requirement: Confirmations stay single and explicit
The system SHALL allow at most one action to await confirmation across all
lanes, and SHALL apply a yes only to the action Sutra has just asked about.

#### Scenario: A background task needs a confirm-first action
- **WHEN** a background request requires a confirm-first tool
- **THEN** it pauses and Sutra asks the user about that specific action
- **AND** nothing runs until the user clearly confirms it

#### Scenario: Two actions wanting confirmation
- **WHEN** a second action needs confirmation while one is already awaiting it
- **THEN** the second is queued and not asked about until the first is settled

#### Scenario: A yes meant for something else
- **WHEN** the user says yes in reply to an announcement that is not a confirmation
- **THEN** no held action is confirmed

### Requirement: Concurrency is capped
The system SHALL limit the number of background requests and SHALL tell the
user plainly when the limit is reached.

#### Scenario: Too many requests
- **WHEN** the limit of background requests is already in use
- **THEN** a new request is declined with a short spoken explanation

### Requirement: Barge-in is optional and off by default
The system SHALL stop speaking and handle new speech when the user interrupts
only if barge-in is enabled.

#### Scenario: Barge-in enabled
- **WHEN** barge-in is on and the user speaks while Sutra is talking
- **THEN** playback stops and the user's words are handled as the next turn

#### Scenario: Barge-in disabled
- **WHEN** barge-in is off and the user speaks while Sutra is talking
- **THEN** Sutra finishes speaking before listening
