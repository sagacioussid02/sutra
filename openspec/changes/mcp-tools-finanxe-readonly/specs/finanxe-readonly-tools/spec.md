## ADDED Requirements

### Requirement: Gateway users can fetch their financial snapshot
The system SHALL expose a `read-only` MCP tool that calls finanxe's
`GET /api/snapshot` and returns the result unmodified in structure.

#### Scenario: Successful snapshot fetch
- **WHEN** an authorized gateway user calls `finanxe_get_snapshot`
- **THEN** the gateway calls finanxe's `/api/snapshot` and returns the response to the caller

#### Scenario: finanxe unreachable
- **WHEN** a gateway user calls `finanxe_get_snapshot` while finanxe's local server is not running
- **THEN** the tool returns an error result indicating finanxe is unreachable, without the gateway crashing or hanging

### Requirement: Gateway users can list debts
The system SHALL expose a `read-only` MCP tool that calls finanxe's
`GET /api/debts` and returns the result unmodified in structure.

#### Scenario: Listing debts
- **WHEN** an authorized gateway user calls `finanxe_list_debts`
- **THEN** the gateway returns the debt list from finanxe's API

### Requirement: Gateway users can fetch their calendar
The system SHALL expose a `read-only` MCP tool that calls finanxe's
`GET /api/calendar` and returns the result unmodified in structure.

#### Scenario: Fetching calendar
- **WHEN** an authorized gateway user calls `finanxe_get_calendar`
- **THEN** the gateway returns the calendar data from finanxe's API

### Requirement: Gateway users can list goals
The system SHALL expose a `read-only` MCP tool that calls finanxe's
`GET /api/goals` and returns the result unmodified in structure.

#### Scenario: Listing goals
- **WHEN** an authorized gateway user calls `finanxe_list_goals`
- **THEN** the gateway returns the goals list, with progress, from finanxe's API

### Requirement: No Plaid or mutating finanxe endpoints are exposed
The system SHALL NOT register any MCP tool that calls a finanxe endpoint
under `/api/plaid/*`, nor any endpoint that creates, updates, or deletes
finanxe state, as part of this capability.

#### Scenario: Plaid endpoints have no corresponding tool
- **WHEN** the gateway's registered tool list is inspected after this change
- **THEN** no tool calls any `/api/plaid/*` finanxe endpoint
