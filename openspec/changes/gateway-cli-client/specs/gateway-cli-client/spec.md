## ADDED Requirements

### Requirement: CLI authenticates with a bearer token
The system SHALL require the CLI client to be started with a bearer token
and SHALL use it to authenticate every gateway call for that session.

#### Scenario: Starting the CLI with a valid token
- **WHEN** the user runs the CLI with a valid bearer token
- **THEN** the CLI connects to the gateway and lists the tools available to that user

#### Scenario: Starting the CLI with an invalid token
- **WHEN** the user runs the CLI with a token the gateway rejects
- **THEN** the CLI reports an authentication error and does not enter the interactive loop

### Requirement: CLI dispatches read-only tool calls directly
The system SHALL, for a `read-only` tool selected by the user, call it and
print the result without any additional confirmation step.

#### Scenario: Calling a read-only tool
- **WHEN** the user selects a `read-only` tool and supplies arguments
- **THEN** the CLI calls the tool through the gateway and prints the result

### Requirement: CLI surfaces confirm-first calls and requires explicit confirmation
The system SHALL, for a `confirm-first` tool call, print the pending
confirmation's human-readable description and require the user to type an
explicit affirmative response before calling the gateway's `confirm()`
operation. Any non-affirmative response SHALL cancel without confirming.

#### Scenario: User confirms a pending action
- **WHEN** the user selects a `confirm-first` tool, supplies arguments, and types the affirmative response to the printed description
- **THEN** the CLI calls the gateway's `confirm()` operation for that pending id
- **AND** prints the resulting outcome

#### Scenario: User declines a pending action
- **WHEN** the user selects a `confirm-first` tool, supplies arguments, and does not type the affirmative response
- **THEN** the CLI does not call `confirm()`
- **AND** the pending action is left to expire per `gateway-core`'s TTL

### Requirement: Walkthrough demonstrates the full Phase 1 path
The system SHALL be documented with a runnable walkthrough covering: a twin
chat call, a finanxe snapshot call, and a finanxe mutating call that is
held for confirmation and then confirmed.

#### Scenario: Following the walkthrough end to end
- **WHEN** a user follows the documented walkthrough with twin and finanxe both reachable
- **THEN** they successfully complete a twin chat, a finanxe snapshot read, and a confirmed finanxe mutation, in one CLI session
