## ADDED Requirements

### Requirement: A project's tools can be discovered from a manifest
The system SHALL fetch and parse a Sutra Agent Manifest
(`GET /.well-known/sutra-agent.json` by convention) describing a backend
project's name and its tools (name, description, tier hint, HTTP
method/path, argument definitions, and whether the tool is safely
callable by a generic HTTP adapter).

#### Scenario: Fetching a well-formed manifest
- **WHEN** discovery is run against a project serving a valid manifest
- **THEN** the system parses every declared tool without error

#### Scenario: Fetching a malformed manifest
- **WHEN** a manifest is missing required fields or uses an unrecognized
  method/type/`in` value
- **THEN** discovery reports every problem found, and does not present any
  tool from that manifest for approval

### Requirement: Discovery never calls a discovered tool
The system SHALL NOT invoke any tool on a backend project as part of
fetching or reviewing its manifest — discovery is read-only against the
manifest endpoint itself.

#### Scenario: Reviewing new tools performs no side effects
- **WHEN** a user runs discovery against a project and reviews its tools
  without approving anything
- **THEN** none of the project's other endpoints have been called

### Requirement: A discovered tool's tier hint is never auto-trusted
The system SHALL treat a manifest tool's `tier_hint` as an untrusted
suggestion only. No tool SHALL be registered with a tier that was not
explicitly chosen by a human during approval.

#### Scenario: Approving requires an explicit typed tier
- **WHEN** a user approves a discovered tool
- **THEN** the system records the tier the user explicitly typed, not the
  manifest's `tier_hint`, even when they match

#### Scenario: A likely mistiered mutating tool is flagged
- **WHEN** a user attempts to approve a tool whose HTTP method is
  `POST`/`PUT`/`PATCH`/`DELETE` as `read-only`
- **THEN** the system warns before recording the approval and requires an
  additional explicit confirmation step

### Requirement: A tool is registered only after explicit approval
The system SHALL NOT register any discovered tool as a callable gateway
tool unless a human has approved it for the exact manifest definition
currently being registered.

#### Scenario: Registering approved tools at startup
- **WHEN** the gateway starts with one or more approved, generically
  callable tools whose current manifest definition matches what was
  approved
- **THEN** those tools appear in the gateway's callable tool list

#### Scenario: Unapproved tools are never registered
- **WHEN** the gateway starts and a discovered tool has not been approved
- **THEN** that tool does not appear in the gateway's callable tool list

#### Scenario: A changed tool definition invalidates its prior approval
- **WHEN** a previously approved tool's manifest entry (method, path,
  args, or description) changes before it is re-approved
- **THEN** the gateway does not register that tool at startup, using
  neither the old nor the new definition

### Requirement: Non-generically-callable tools require a hand-written adapter
The system SHALL record an approval decision (including tier) for a tool
marked `generic_callable: false`, but SHALL NOT register it as callable
through the generic adapter.

#### Scenario: Approving a bespoke tool does not make it callable
- **WHEN** a user approves a tool marked `generic_callable: false`
- **THEN** the approval is recorded
- **AND** the tool does not appear in the gateway's callable tool list
  until a hand-written adapter registers it separately

### Requirement: Rejected tools are resurfaced, not permanently hidden
The system SHALL present a previously rejected tool again on a future
discovery run rather than suppressing it indefinitely.

#### Scenario: A rejected tool reappears for review
- **WHEN** discovery is run again against a project with a previously
  rejected tool still present in its manifest
- **THEN** that tool is shown for review again

### Requirement: Secret arguments are redacted regardless of tool origin
The system SHALL redact any argument a manifest declares `secret: true` in
the audit log, using the same redaction mechanism applied to hand-written
tools.

#### Scenario: A generically registered tool's secret argument is redacted
- **WHEN** a generically registered tool declaring a secret argument is
  called
- **THEN** the audit log entry masks that argument's value
