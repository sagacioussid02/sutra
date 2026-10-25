## ADDED Requirements

### Requirement: Every gateway request requires a bearer token
The system SHALL require a valid bearer token on every tool-call and
confirmation request. The system SHALL reject unauthenticated requests
without invoking any tool.

#### Scenario: Missing token is rejected
- **WHEN** a client calls a tool without a bearer token
- **THEN** the gateway returns an authentication error and does not invoke the tool or write a "pending"/"executed" audit entry beyond the denial itself

#### Scenario: Invalid token is rejected
- **WHEN** a client calls a tool with a bearer token not present in the token configuration
- **THEN** the gateway returns an authentication error

### Requirement: Tokens map to a user identity and an allowed-tools set
The system SHALL resolve each valid bearer token to a user identity and a
set of tool names that user is permitted to call, loaded from local
configuration at startup.

#### Scenario: User calls a tool outside their allowed set
- **WHEN** an authenticated user calls a tool not included in their allowed-tools set
- **THEN** the gateway denies the call with an authorization error
- **AND** records the denial in the audit log with the user's identity

#### Scenario: User calls a tool within their allowed set
- **WHEN** an authenticated user calls a tool included in their allowed-tools set
- **THEN** the gateway proceeds to the tool's tier-specific handling (immediate execution or confirmation flow)

### Requirement: Token configuration is not committed to version control
The system SHALL load the token -> user -> allowed-tools mapping from a
local, gitignored configuration file, not from source code or a committed
config file.

#### Scenario: Repo contains no real tokens
- **WHEN** the repository is inspected
- **THEN** no bearer token values appear in any tracked file
