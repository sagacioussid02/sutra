## ADDED Requirements

### Requirement: Every tool call attempt is recorded
The system SHALL record an audit log entry for every tool-call attempt that
reaches the gateway's authorization check or beyond, including denials,
pending confirmations, confirmed executions, direct executions, and errors.
Each entry SHALL include a timestamp, the caller's user identity, the tool
name, the outcome status, and a result summary.

#### Scenario: Denied call is logged
- **WHEN** a user calls a tool outside their allowed-tools set
- **THEN** an audit log entry is written with status `denied`, the user's identity, and the tool name

#### Scenario: Executed read-only call is logged
- **WHEN** a `read-only` tool call executes successfully
- **THEN** an audit log entry is written with status `executed` and a summary of the result

#### Scenario: Confirm-first lifecycle is logged at each step
- **WHEN** a `confirm-first` tool call is requested, then later confirmed and executed
- **THEN** the audit log contains a `pending` entry at request time and a separate `executed` entry at confirmation time, linked by the pending confirmation id

### Requirement: Secret-bearing arguments are redacted before logging
The system SHALL redact argument values that a tool registration marks as
secret before writing them to the audit log, replacing the value with a
fixed redaction marker rather than omitting the field.

#### Scenario: Secret argument is masked, not logged in plaintext
- **WHEN** a tool call includes an argument marked secret in its tool registration
- **THEN** the corresponding audit log entry shows a redaction marker for that argument, not its real value

### Requirement: Audit log is queryable after the fact
The system SHALL persist audit log entries durably (surviving a gateway
restart) in a form that can be queried by user, tool name, status, or time
range without parsing free-text log files.

#### Scenario: Audit entries survive a restart
- **WHEN** the gateway process is restarted after logging tool-call attempts
- **THEN** previously written audit log entries are still present and queryable
