## ADDED Requirements

### Requirement: A typed turn runs the identical pipeline
A turn submitted through the chat surface SHALL be processed by the
same turn handler as a turn from the voice client or the REPL: the
same memory recall and recording, the same tools through the
gateway, the same confirmation flow, and the same offers arbiter.
The chat surface SHALL NOT maintain its own prompt, tool set, memory,
or safety behaviour.

#### Scenario: Confirm-first request in chat
- **WHEN** a chat turn asks for a confirm-first action
- **THEN** the turn produces a pending confirmation, exactly as the same utterance does by voice, and nothing is executed

#### Scenario: Slash commands in chat
- **WHEN** the user enters a control command such as `/state` or `/inbox` in chat
- **THEN** the same command handler answers as in the REPL

### Requirement: Replies stream, and tool and confirmation states are visible
The surface SHALL render a reply incrementally as the pipeline
produces it. Tool calls SHALL be shown in the transcript with the
tool's name and outcome, and a pending confirmation SHALL be shown
as a distinct state identifying what is being confirmed. Streaming
and rendering SHALL NOT alter the turn's processing or its final
reply.

#### Scenario: Streamed reply matches the assembled reply
- **WHEN** a scripted session is run through chat with streaming and through the REPL
- **THEN** the final replies are identical, and the chat transcript shows the tool actions the session performed

#### Scenario: Action review after the fact
- **WHEN** a completed session is reopened from the transcript
- **THEN** each action the assistant took is visible with its tool name and whether it succeeded

### Requirement: Confirmations are answered in words, through the classifier
A pending confirmation in chat SHALL be answered by a typed user
reply, which SHALL be passed to the existing confirmation classifier
under the same isolation as a spoken reply. The surface SHALL NOT
provide any control — button, shortcut, or gesture — that confirms
or denies a pending confirmation without a classified user reply.

#### Scenario: Clear affirmation confirms
- **WHEN** a confirmation is pending and the user types an unambiguous affirmation
- **THEN** the classified reply confirms the action, as the same words would by voice

#### Scenario: Sarcasm does not confirm
- **WHEN** a confirmation is pending and the user types a reply the classifier does not read as an affirmation
- **THEN** the action is not executed and the confirmation remains governed by the classifier's outcome, exactly as by voice

### Requirement: The transcript persists per user and is not a memory
The surface SHALL persist the transcript — user turns, replies, tool
actions and outcomes, and confirmation states — per user, in a local
store with the protections of the other per-user stores, surviving
restarts. The transcript SHALL NOT be used as an input to the
assistant's memory or recall; memory recording SHALL remain the
pipeline's own, unchanged by the surface.

#### Scenario: Session resumes after restart
- **WHEN** the orchestrator restarts and the user reopens chat
- **THEN** the earlier transcript is shown, including actions taken and their outcomes

#### Scenario: Transcript does not become memory
- **WHEN** a fact appears in a chat transcript but was never recorded by the pipeline's memory interface
- **THEN** the assistant does not recall it in a later session

### Requirement: The debug toggle reveals decisions and changes nothing
With debug mode enabled, the surface SHALL annotate turns with the
pipeline's recorded decisions: whether a turn was consumed as a
confirmation reply and its classification, offers created or
deferred with the arbiter's recorded reason, and snapshot fields
shown stale. Debug mode SHALL be off by default and SHALL NOT change
any processing outcome.

#### Scenario: Deferral explained
- **WHEN** debug mode is on and an offer is deferred during the session
- **THEN** the transcript annotation names the deferral and the reason the arbiter recorded

#### Scenario: Toggle off hides, toggle on reveals, outcomes identical
- **WHEN** the same scripted session is run with debug mode off and on
- **THEN** the decisions and outcomes are identical, and only the annotations differ

### Requirement: The surface is local and authenticated
The chat server SHALL bind localhost by default; binding any other
interface SHALL require explicit configuration. Every request SHALL
require the same bearer-token authentication the orchestrator
already uses. Until `per-user-identity` lands, the surface SHALL
serve a single owner's session, and that assumption SHALL be stated
in its documentation.

#### Scenario: Unauthenticated request
- **WHEN** a request arrives without a valid token
- **THEN** it is rejected and no turn is processed

#### Scenario: Default bind
- **WHEN** the chat server starts with default configuration
- **THEN** it accepts connections only on the local interface

### Requirement: Failure closes actions and degrades the surface honestly
If a turn's stream fails or the surface disconnects mid-turn, the
turn SHALL be marked failed in the transcript and no confirm-first
action SHALL complete from that turn; a pending confirmation SHALL
remain pending until answered by a new, complete turn. If the
gateway is unreachable, the surface SHALL report unavailability and
SHALL NOT render a fabricated reply.

#### Scenario: Stream drops mid-turn
- **WHEN** the connection fails while a turn that raised a confirmation is streaming
- **THEN** nothing is executed, the transcript marks the turn failed, and the confirmation is still pending

#### Scenario: Gateway down
- **WHEN** a chat turn is submitted while the gateway is unreachable
- **THEN** the surface reports that the assistant cannot reach its tools, and no reply is invented

### Requirement: Voice-only behaviours are absent from chat
The chat surface SHALL NOT apply spoken-delivery behaviour: no
fillers, no sentence-splitting for speech, and no interruption
handling. The text a chat user sees SHALL be the pipeline's reply,
formatted only by the rendering of states and actions.

#### Scenario: Plain reply in chat
- **WHEN** an ordinary question is answered in chat
- **THEN** the reply contains no spoken-delivery artefacts and matches the reply the REPL returns for the same turn
