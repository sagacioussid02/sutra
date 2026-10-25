## ADDED Requirements

### Requirement: Confirm-first calls do not execute immediately
The system SHALL, upon an authorized call to a `confirm-first` tool, create
a pending confirmation record and return its id and a human-readable
description of the action instead of executing the tool.

#### Scenario: Confirm-first call returns pending, not a result
- **WHEN** an authenticated, authorized user calls a `confirm-first` tool
- **THEN** the gateway does not invoke the underlying tool
- **AND** returns a pending confirmation id and a description of what would happen if confirmed

### Requirement: Confirming a pending call executes the original tool
The system SHALL provide a `confirm(pending_id)` operation that, given a
valid, non-expired pending confirmation id belonging to the requesting user,
executes the original tool call with its original arguments and returns the
result.

#### Scenario: Valid confirmation executes the held call
- **WHEN** the user who created a pending confirmation submits `confirm(pending_id)` before it expires
- **THEN** the gateway executes the originally requested tool call with the original arguments
- **AND** returns the tool's result

#### Scenario: Confirming another user's pending call is rejected
- **WHEN** a user submits `confirm(pending_id)` for a pending confirmation created by a different user
- **THEN** the gateway rejects the confirmation and does not execute the tool

### Requirement: Pending confirmations expire
The system SHALL expire a pending confirmation after a configured TTL. The
system SHALL reject a `confirm()` call against an expired or already-used
pending id.

#### Scenario: Expired confirmation cannot be executed
- **WHEN** a user submits `confirm(pending_id)` after the pending confirmation's TTL has elapsed
- **THEN** the gateway rejects the confirmation with an expiration error
- **AND** does not execute the tool

#### Scenario: Already-confirmed id cannot be reused
- **WHEN** a user submits `confirm(pending_id)` for a pending confirmation that was already confirmed and executed
- **THEN** the gateway rejects the second confirmation and does not execute the tool a second time
