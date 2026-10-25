## ADDED Requirements

### Requirement: Redirecting debt funding requires confirmation
The system SHALL expose a `confirm-first` MCP tool that, once confirmed,
calls finanxe's `POST /api/debt/funding` to redirect funding for a named
debt to a named account. Calling the tool directly SHALL only create a
pending confirmation, per `gateway-core`'s confirm-first flow.

#### Scenario: Requesting the change returns a pending confirmation
- **WHEN** an authorized gateway user calls `finanxe_set_debt_funding` with a debt name and account
- **THEN** the gateway does not call finanxe yet
- **AND** returns a pending confirmation id and a description naming the debt and account involved

#### Scenario: Confirming executes the change
- **WHEN** the user confirms the pending id from `finanxe_set_debt_funding`
- **THEN** the gateway calls finanxe's `/api/debt/funding` with the original arguments
- **AND** returns finanxe's result to the caller

### Requirement: Creating a tracked goal requires confirmation
The system SHALL expose a `confirm-first` MCP tool that, once confirmed,
calls finanxe's `POST /api/goals/add` to create a new tracked goal.

#### Scenario: Requesting goal creation returns a pending confirmation
- **WHEN** an authorized gateway user calls `finanxe_create_goal` with goal details
- **THEN** the gateway returns a pending confirmation id and a description of the goal to be created, without creating it yet

#### Scenario: Confirming creates the goal
- **WHEN** the user confirms the pending id from `finanxe_create_goal`
- **THEN** the gateway calls finanxe's `/api/goals/add` with the original arguments
- **AND** returns finanxe's result to the caller

### Requirement: Adding a calendar event requires confirmation
The system SHALL expose a `confirm-first` MCP tool that, once confirmed,
calls finanxe's `POST /api/calendar/event` to add a calendar event.

#### Scenario: Requesting event creation returns a pending confirmation
- **WHEN** an authorized gateway user calls `finanxe_add_calendar_event` with a title and date
- **THEN** the gateway returns a pending confirmation id and a description of the event to be added, without creating it yet

#### Scenario: Confirming adds the event
- **WHEN** the user confirms the pending id from `finanxe_add_calendar_event`
- **THEN** the gateway calls finanxe's `/api/calendar/event` with the original arguments
- **AND** returns finanxe's result to the caller

### Requirement: No unconfirmed finanxe mutation is possible through the gateway
The system SHALL NOT execute any finanxe mutating endpoint as a direct
result of the initial tool call for `finanxe_set_debt_funding`,
`finanxe_create_goal`, or `finanxe_add_calendar_event` — execution SHALL
only occur through `gateway-core`'s confirmation step.

#### Scenario: Tool call alone never mutates finanxe state
- **WHEN** any of the three mutating tools is called without a subsequent confirmation
- **THEN** finanxe's underlying data is unchanged
