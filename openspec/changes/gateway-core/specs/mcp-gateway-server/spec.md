## ADDED Requirements

### Requirement: Gateway runs as a single local MCP server
The system SHALL run as a single local MCP server process reachable only on
localhost in Phase 1, implementing the MCP protocol so any MCP-compatible
client can connect.

#### Scenario: Gateway starts and exposes no tools by default
- **WHEN** the gateway process starts with no adapters registered
- **THEN** it accepts MCP connections and reports an empty tool list

### Requirement: Tools are registered with a mandatory tier
The system SHALL require every tool registered with the gateway to declare
exactly one tier: `read-only`, `confirm-first`, or `never-by-voice`. The
system SHALL reject registration of a tool with no tier or an unrecognized
tier.

#### Scenario: Registering a tool without a tier fails
- **WHEN** an adapter attempts to register a tool without specifying a tier
- **THEN** the gateway refuses the registration and raises a startup error identifying the offending tool

### Requirement: Never-by-voice tools are not exposed as callable
The system SHALL exclude `never-by-voice` tools from the callable tool list
returned to any client, while still allowing them to exist in the registry
for future use.

#### Scenario: Never-by-voice tool is registered but not listed
- **WHEN** an adapter registers a tool tiered `never-by-voice`
- **THEN** the tool does not appear in the MCP tool list returned to clients
- **AND** calling it by name returns a not-found error, not the tool's result

### Requirement: Read-only tools execute immediately
The system SHALL execute `read-only` tool calls immediately upon receiving a
valid, authorized request, without a confirmation step.

#### Scenario: Authorized read-only call executes
- **WHEN** an authenticated user with access calls a `read-only` tool with valid arguments
- **THEN** the gateway invokes the tool and returns its result in the same request
