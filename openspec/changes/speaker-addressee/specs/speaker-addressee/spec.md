## ADDED Requirements

### Requirement: Every voice utterance carries a speaker signal
The system SHALL attach to each voice utterance a speaker signal giving
either an enrolled speaker id or `unknown`, with a confidence and the
identification method. The system SHALL NOT guess an identity for an
unenrolled voice.

#### Scenario: Enrolled speaker speaks
- **WHEN** an enrolled speaker speaks in a session
- **THEN** the utterance carries that speaker's id with its confidence

#### Scenario: Unenrolled voice speaks
- **WHEN** a voice with no enrolment profile speaks
- **THEN** the utterance's signal is `unknown`

### Requirement: Enrolment is explicit, scoped, and revocable
The system SHALL enrol a speaker only through a deliberate enrolment
flow started by the user, one profile per person, stored locally with
owner-only permissions. Enrolled speakers SHALL be listed on the control
surface and a profile SHALL be deletable, taking effect immediately. The
default enrolment scope SHALL be the owner only.

#### Scenario: Enrolling a second person
- **WHEN** the user runs the enrolment flow for a family member
- **THEN** a profile is created for that person, mapped to their user id, and appears in the enrolled list

#### Scenario: Revoking enrolment
- **WHEN** the user deletes a speaker profile
- **THEN** that voice is `unknown` from the next utterance onward

#### Scenario: No opportunistic enrolment
- **WHEN** an unenrolled voice is heard in conversation
- **THEN** no profile is created for it

### Requirement: Addressee detection gates response and action
In an open conversation, the system SHALL classify each utterance as
addressed to the assistant, addressed elsewhere, or unclear. Speech
addressed elsewhere SHALL NOT trigger replies, offers, or tools. An
action (a tool call, a confirmation, a write) SHALL require an
*addressed* classification; an answer MAY proceed on *addressed* or
*unclear*. When no conversation is open, no speech SHALL be treated as
addressed until the assistant is opened as it is today.

#### Scenario: Talking to someone else in the room
- **WHEN** the user, mid-conversation, speaks to another person present
- **THEN** the assistant does not reply, offer, or call any tool for that utterance

#### Scenario: Ambiguous utterance before an action
- **WHEN** an utterance is classified unclear and its handling would invoke a tool
- **THEN** the tool is not invoked for that utterance

#### Scenario: Direct question
- **WHEN** the user addresses a question to the assistant in an open conversation
- **THEN** the assistant answers it normally

### Requirement: Confirmations honour only the bound speaker's signal
A confirmation for a pending claim SHALL be accepted only when the
confirming utterance's speaker signal matches the speaker the claim is
bound to and its confidence meets the configured threshold. A
confirmation-shaped utterance from any other speaker SHALL be ignored
for that claim and recorded in the audit.

#### Scenario: Bound speaker confirms
- **WHEN** the speaker a claim is bound to confirms at sufficient confidence
- **THEN** the confirmed action proceeds as it does today

#### Scenario: Different speaker attempts to confirm
- **WHEN** a different enrolled speaker says "yes" while a claim bound to the owner is pending
- **THEN** the claim is not executed, the attempt is audited, and the claim remains pending until it expires

#### Scenario: Feature disabled
- **WHEN** the speaker feature switch is off
- **THEN** utterances carry no signal and confirmation behaviour is unchanged from before this change
