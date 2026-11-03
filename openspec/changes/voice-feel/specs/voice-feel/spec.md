## ADDED Requirements

### Requirement: Replies are spoken as they are written

When streaming is on, the system SHALL speak a reply sentence by sentence while the model is still writing it, starting with the first complete sentence. It SHALL release a sentence only when the next has begun or the stream has ended, SHALL drop held text when a model step ends with a tool call, and SHALL NOT split a sentence at an abbreviation or a number with a decimal point. The reply the orchestrator returns and records SHALL be the full reply.

#### Scenario: First sentence early

- **WHEN** the model writes three sentences
- **THEN** the first is spoken before the third has been written

#### Scenario: A tool call after a short lead-in

- **WHEN** a model step writes one sentence and then calls a tool
- **THEN** that sentence is not spoken

#### Scenario: Abbreviations

- **WHEN** a reply contains "Dr. Rao at 3.5 percent, around 5 p.m. today."
- **THEN** it is not split inside that sentence

### Requirement: Nothing is lost or said twice

The voice client SHALL speak whatever part of the final reply was not streamed (such as an appended offer) after the streamed sentences, and SHALL speak the whole reply if the streamed text is not the start of the reply. If streaming fails, the system SHALL speak the whole reply as without streaming.

#### Scenario: An offer appended after streaming

- **WHEN** a reply is streamed and an offer is appended to it
- **THEN** the offer is spoken after the streamed sentences, and the streamed sentences are not repeated

#### Scenario: Streaming fails

- **WHEN** the stream raises an error part-way
- **THEN** the full reply is spoken and the turn completes

### Requirement: Speaking over a streamed reply works

While streamed sentences are spoken, the voice client SHALL apply the same speak-over behaviour as for any reply: a cut-in stops the voice, discards the sentences not yet spoken, lets the model finish quietly, and treats what the user said as their next turn.

#### Scenario: Cut in mid-reply

- **WHEN** the user speaks over the second sentence of a streamed reply
- **THEN** speech stops, the remaining sentences are not spoken, and the user's words are answered next

### Requirement: Acknowledgements are instant

The speaker SHALL keep short phrases (up to 40 characters, at most 24 of them) in memory after their first synthesis and replay them without a network call, SHALL pre-synthesize the filler phrases at start, and SHALL NOT let a failure to pre-synthesize stop the session. A filler SHALL NOT be spoken once a streamed sentence has started.

#### Scenario: A repeated filler

- **WHEN** the same filler is spoken twice
- **THEN** only the first causes a synthesis request

#### Scenario: A reply that streams quickly

- **WHEN** the first streamed sentence arrives before the filler delay
- **THEN** no filler is spoken

### Requirement: Delivery can be tuned

The system SHALL take the text-to-speech style instructions from `SUTRA_TTS_STYLE` when set and otherwise use a built-in default.

#### Scenario: A custom style

- **WHEN** `SUTRA_TTS_STYLE` is set
- **THEN** speech requests carry that text as their style instructions

### Requirement: Turn timing is visible

With verbose logging the system SHALL log, for each voice turn, the time spent hearing and transcribing, the time from request to reply, and the time from request to the first spoken sentence, and SHALL log nothing extra otherwise.

#### Scenario: Verbose

- **WHEN** a turn runs with verbose logging
- **THEN** the three timings are logged
