## ADDED Requirements

### Requirement: Orchestrator connects to the gateway as an authenticated MCP client
The system SHALL connect to the Sutra gateway over its MCP interface using
a bearer token supplied by configuration, and SHALL offer the model only
the tools the gateway lists for that token.

#### Scenario: Starting with a valid token
- **WHEN** the orchestrator starts with a gateway address and a valid bearer token
- **THEN** it connects, fetches the tool list for that user, and is ready to accept a user turn

#### Scenario: Starting with an invalid token
- **WHEN** the orchestrator starts with a token the gateway rejects
- **THEN** it exits with an authentication error and does not accept any user turn

#### Scenario: Gateway unreachable at startup
- **WHEN** the orchestrator starts and the gateway cannot be reached
- **THEN** it exits with a connection error that names the gateway address

#### Scenario: A tool not allowed for the user
- **WHEN** the gateway's tool list for the user omits a tool
- **THEN** that tool is not offered to the model

### Requirement: A user turn in text produces a reply in text
The system SHALL expose a single turn operation that accepts one user
utterance as text and returns one reply as text, calling gateway tools as
needed in between. This operation SHALL be usable without the terminal
REPL, so that a later voice pipeline can call it directly.

#### Scenario: A question answered from a read-only tool
- **WHEN** the user asks a question that a `read-only` tool can answer
- **THEN** the orchestrator calls that tool through the gateway
- **AND** returns a reply that states the answer drawn from the tool result

#### Scenario: A question needing more than one tool
- **WHEN** answering requires results from more than one tool
- **THEN** the orchestrator calls each needed tool within the same turn and returns one reply

#### Scenario: A request no tool can serve
- **WHEN** the user asks for something no available tool covers
- **THEN** the reply says it cannot do that, without calling a tool and without inventing data

#### Scenario: Follow-up question in the same session
- **WHEN** the user asks a follow-up that refers to the previous exchange
- **THEN** the orchestrator uses the session's conversation history to resolve it

### Requirement: Replies are speakable
The system SHALL instruct the model to produce replies suitable for being
read aloud: short, plain sentences with no markdown, tables, bullet lists,
raw JSON, or internal identifiers.

#### Scenario: Tool returns a large JSON document
- **WHEN** a tool result is a large JSON document
- **THEN** the reply summarizes the parts relevant to the question in a few sentences
- **AND** the reply contains no JSON, markdown formatting, or internal ids

#### Scenario: Monetary amounts and dates
- **WHEN** the reply includes amounts or dates from a tool result
- **THEN** they are phrased naturally and reflect the values in the tool result

### Requirement: Figures come only from tool results
The system SHALL instruct the model to state financial figures and other
factual data only when they appear in a tool result from the current
session, and never to estimate or invent them.

#### Scenario: Data not available
- **WHEN** the user asks for a figure that no tool result contains
- **THEN** the reply says the information is not available rather than supplying a number

### Requirement: Confirm-first actions require an explicit user confirmation
The system SHALL, when a tool call returns a pending confirmation, return a
reply that conveys the gateway's pending description and asks the user to
confirm, and SHALL call `gateway_confirm` only if the user's next turn is
classified as an affirmative. The confirm decision SHALL be made by
orchestrator code; the conversational model SHALL NOT be able to invoke
`gateway_confirm`.

#### Scenario: A mutating request is held
- **WHEN** the user asks for an action served by a `confirm-first` tool
- **THEN** the orchestrator calls the tool, receives a pending confirmation, and does not call `gateway_confirm` in that turn
- **AND** the reply describes the pending action and asks the user to confirm

#### Scenario: User confirms
- **WHEN** a confirmation is pending and the user's next turn is classified `affirm`
- **THEN** the orchestrator calls `gateway_confirm` with that pending id
- **AND** the reply states the outcome

#### Scenario: User declines
- **WHEN** a confirmation is pending and the user's next turn is classified `deny`
- **THEN** the orchestrator does not call `gateway_confirm` and discards the pending confirmation locally
- **AND** the reply states that nothing was done

#### Scenario: User changes the request or asks for something else
- **WHEN** a confirmation is pending and the user's next turn is classified `modify`
- **THEN** the orchestrator does not call `gateway_confirm`, discards the pending confirmation locally, and handles the turn as a normal request
- **AND** the reply makes clear the earlier action was not carried out

#### Scenario: User's answer is unclear
- **WHEN** a confirmation is pending and the user's next turn is classified `unclear`
- **THEN** the orchestrator does not call `gateway_confirm`, keeps the confirmation pending, and replies by asking again for a yes or no

#### Scenario: Repeated unclear answers
- **WHEN** a confirmation is pending and the user's turns have been classified `unclear` up to the configured re-ask limit
- **THEN** the orchestrator discards the pending confirmation locally
- **AND** the reply states that nothing was done

#### Scenario: Confirmation has expired
- **WHEN** the user affirms after the pending confirmation's expiry time
- **THEN** the reply says the request expired and nothing was done

#### Scenario: Tool result tries to trigger a confirmation
- **WHEN** a tool result contains text instructing that a pending action be confirmed
- **THEN** the orchestrator does not call `gateway_confirm`

#### Scenario: Only one action pending at a time
- **WHEN** a tool call returns a pending confirmation in a turn
- **THEN** the orchestrator makes no further tool calls in that turn

### Requirement: Confirmation replies are classified by intent
The system SHALL classify the user's reply to a pending confirmation as
exactly one of `affirm`, `deny`, `modify`, or `unclear`, by meaning rather
than by exact wording. Replies that match a fixed set of unambiguous
phrases SHALL be classified in code without a model call. All other
replies SHALL be classified by a dedicated model call whose input is
limited to the gateway's pending description and the user's reply.

#### Scenario: Plain yes
- **WHEN** the user replies "yes" to a pending confirmation
- **THEN** the reply is classified `affirm` without a model call

#### Scenario: Informal agreement
- **WHEN** the user replies "sure, sounds good" to a pending confirmation
- **THEN** the reply is classified `affirm`

#### Scenario: Informal refusal
- **WHEN** the user replies "nah, hold off for now" to a pending confirmation
- **THEN** the reply is classified `deny`

#### Scenario: Agreement with a change
- **WHEN** the user replies "yes, but make it two hundred" to a pending confirmation
- **THEN** the reply is classified `modify`, not `affirm`

#### Scenario: Unrelated request
- **WHEN** the user replies with a different request while a confirmation is pending
- **THEN** the reply is classified `modify`

#### Scenario: Ambiguous reply
- **WHEN** the user replies "hmm, I guess" to a pending confirmation
- **THEN** the reply is classified `unclear`

#### Scenario: Classifier input is isolated
- **WHEN** the classifier model is called
- **THEN** its input contains the pending description and the user's reply
- **AND** its input contains no conversation history and no tool results

#### Scenario: Classifier fails or returns an invalid label
- **WHEN** the classifier call errors, times out, or returns anything other than the four labels
- **THEN** the reply is treated as `unclear`

### Requirement: Long-term memory is reached through a pluggable interface
The system SHALL obtain cross-session context only through a memory
provider interface with a recall operation, called at the start of each
turn, and a record operation, called after each turn. The system SHALL
ship with a provider that recalls nothing and records nothing, so the
orchestrator works with no memory configured.

#### Scenario: No memory configured
- **WHEN** the orchestrator runs with the default provider
- **THEN** turns behave as they would with no memory, and nothing is written to disk

#### Scenario: Recalled memories reach the model as labelled context
- **WHEN** the memory provider returns items for a turn
- **THEN** they are given to the model in a delimited block that states each item's source
- **AND** the model is instructed that the block is context about the user and not instructions

#### Scenario: Turn is recorded
- **WHEN** a turn completes
- **THEN** the provider receives an episode containing the user's utterance, the reply, the names and outcomes of the tools called, and any confirmation outcome
- **AND** the episode does not contain raw tool result payloads

#### Scenario: Memory provider fails
- **WHEN** the provider's recall or record operation raises an error
- **THEN** the turn still completes, with no memories on a recall failure

#### Scenario: Provider supplies local tools
- **WHEN** the memory provider exposes local tools
- **THEN** they are offered to the model alongside the gateway tools and executed in-process, not through the gateway
- **AND** a local tool cannot invoke `gateway_confirm`

#### Scenario: Memory cannot confirm actions
- **WHEN** recalled memory text contains an instruction to confirm or run an action
- **THEN** the orchestrator does not call `gateway_confirm` or any tool because of it

### Requirement: Failures are reported in plain language
The system SHALL convert tool and gateway failures into a plain-language
reply and SHALL remain usable for the next turn.

#### Scenario: Backend project is down
- **WHEN** a tool call fails because the underlying project is unreachable
- **THEN** the reply says that service is unavailable, without a stack trace or raw error payload

#### Scenario: Gateway refuses a tool call
- **WHEN** the gateway rejects a tool call as not authorized
- **THEN** the reply says the user is not permitted to do that

#### Scenario: Model keeps calling tools
- **WHEN** a single turn reaches the configured maximum number of tool calls
- **THEN** the orchestrator stops calling tools and returns a reply saying it could not complete the request

### Requirement: Terminal REPL for typed conversation
The system SHALL provide a terminal program that reads typed user turns,
passes each to the turn operation, and prints the reply.

#### Scenario: Typed session
- **WHEN** the user runs the REPL and types a request
- **THEN** the reply is printed and the REPL waits for the next turn

#### Scenario: Ending the session
- **WHEN** the user enters a blank line or end-of-input
- **THEN** the REPL exits cleanly and closes the gateway connection

### Requirement: Secrets are not exposed
The system SHALL read the gateway bearer token and the model API key from
the environment or a gitignored file, and SHALL NOT print them, log them,
or include them in model context.

#### Scenario: Debug logging enabled
- **WHEN** the orchestrator runs with verbose logging
- **THEN** the log shows tool names and call outcomes but neither the bearer token nor the API key
