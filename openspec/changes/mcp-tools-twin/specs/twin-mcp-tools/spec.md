## ADDED Requirements

### Requirement: Gateway users can chat with a twin persona
The system SHALL expose a `read-only` MCP tool that, given a twin id and a
message, calls twin's `/chat` API and returns the persona's reply.

#### Scenario: Successful chat call
- **WHEN** an authorized gateway user calls `twin_chat` with a valid `twin_id` and message
- **THEN** the gateway calls twin's `/chat` endpoint and returns the reply text to the caller

#### Scenario: Unknown twin id
- **WHEN** a gateway user calls `twin_chat` with a `twin_id` that twin's API reports as not found
- **THEN** the tool returns an error result indicating the twin was not found, without the gateway crashing or hanging

### Requirement: Conversation continuity per gateway user
The system SHALL derive a stable session identifier from the calling
gateway user's identity and the target twin id, so repeated `twin_chat`
calls from the same gateway user against the same twin continue the same
underlying twin conversation.

#### Scenario: Same user, same twin, continued conversation
- **WHEN** the same gateway user calls `twin_chat` twice against the same `twin_id`
- **THEN** both calls use the same derived session id
- **AND** twin's reply to the second call reflects context from the first (per twin's own session-based memory)

### Requirement: Gateway users can list public personas
The system SHALL expose a `read-only` MCP tool that calls twin's
`/public-personas` endpoint and returns the list of available personas.

#### Scenario: Listing personas
- **WHEN** an authorized gateway user calls `twin_list_public_personas`
- **THEN** the gateway returns the persona list from twin's API unmodified in structure
