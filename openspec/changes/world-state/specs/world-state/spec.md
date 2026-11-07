## ADDED Requirements

### Requirement: The snapshot is assembled on demand for one user
The system SHALL assemble a world-state snapshot for exactly one user —
the user the current caller maps to under `per-user-identity` — at the
first read in a turn, and SHALL reuse that assembly for the rest of the
turn. The system SHALL NOT persist the snapshot as a record of truth.

#### Scenario: Turn-start assembly
- **WHEN** a turn begins and a consumer reads the snapshot
- **THEN** a snapshot is assembled from the current sources and reused for subsequent reads in that turn

#### Scenario: Single user
- **WHEN** a snapshot is assembled
- **THEN** every field is read from the mapped user's stores and tool views only

### Requirement: Every field carries source, age, and staleness
Each snapshot field SHALL record its source and the time it was observed,
and SHALL be flagged stale once older than its configured TTL. Rendered
for the model, a field SHALL show its age inline, and a stale field SHALL
be marked as stale.

#### Scenario: Fresh field
- **WHEN** the calendar field was observed two minutes ago and its TTL is five minutes
- **THEN** the field is presented with its age and is not marked stale

#### Scenario: Stale field
- **WHEN** a field is older than its TTL at render time
- **THEN** it is marked stale with its age, or omitted — never presented as current

#### Scenario: Guaranteed-fresh read
- **WHEN** a code path demands a field with a maximum age lower than the cached field's age
- **THEN** that field alone is re-assembled before the read returns

### Requirement: Unobservable fields are absent, never guessed
When a source errors, times out, or is unavailable, the snapshot SHALL
omit that field. The system SHALL NOT fill a missing field from memory,
from a previous snapshot, or from inference.

#### Scenario: Calendar tool unavailable
- **WHEN** the calendar read fails during assembly
- **THEN** the snapshot has no calendar field and assembly succeeds

#### Scenario: No memory backfill
- **WHEN** a field is absent and a related memory exists
- **THEN** the field remains absent; the memory is available only through normal recall, labelled as memory

### Requirement: Financial state is a pointer, not a copy
The finance field of the snapshot SHALL identify the latest finanxe
snapshot and when it was taken, and SHALL NOT contain financial figures.

#### Scenario: Finance field content
- **WHEN** a snapshot is assembled
- **THEN** its finance field names the source snapshot and its time, and contains no balances, debts, or totals

### Requirement: Open commitments are reported from their owning stores
The snapshot SHALL report pending confirmations, unanswered offers,
active reminders, and episode-graph open items, read at assembly time
from the stores that own them. The snapshot SHALL NOT itself create,
resolve, or expire a commitment.

#### Scenario: Just-created reminder
- **WHEN** a reminder is created and a snapshot is assembled afterwards
- **THEN** the commitments field includes that reminder

#### Scenario: Resolved offer
- **WHEN** an offer is answered and a new snapshot is assembled
- **THEN** the offer no longer appears as open
