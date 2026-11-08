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

### Requirement: Principal state enters the snapshot only from declared sources
The snapshot SHALL include a principal section — availability windows,
a daily attention budget in minutes, major commitments with end dates,
and an effort-sensitivity preference — read only from user-declared
settings and user-confirmed entries for the snapshot's user. The system
SHALL NOT derive any principal field from observed behaviour, and SHALL
NOT read a calendar to construct one in this change.

#### Scenario: Declared budget appears
- **WHEN** the user has declared a daily attention budget and a snapshot is assembled
- **THEN** the principal section shows the budget with its source and the time it was set

#### Scenario: Nothing declared
- **WHEN** the user has declared no principal state
- **THEN** the snapshot has no principal section, however the user's recent behaviour looks

#### Scenario: Commitment recorded as stated
- **WHEN** the user declares a major commitment with an end date
- **THEN** the principal section records it with that end date, unchanged by inference

### Requirement: Principal fields obey the same staleness rules
Each principal field SHALL record its source and the time it was set,
and SHALL be presented with its age. A major commitment SHALL be
presented as current only up to its stated end date; past that date it
SHALL be marked ended or omitted — never presented as still current. A
principal field treated as stale SHALL be excluded from budgeting
decisions while remaining visible as stale in the rendered snapshot.

#### Scenario: Expired commitment
- **WHEN** a snapshot is assembled after a commitment's end date
- **THEN** the commitment is marked ended or omitted, and no consumer treats it as current

#### Scenario: Stale budget not applied
- **WHEN** the declared attention budget is stale at offer time
- **THEN** the arbiter does not apply it and falls back to the existing offer cap

### Requirement: Offers carry a user-effort estimate
The ask-first arbiter SHALL attach an estimated user-effort to every
offer it considers: an amount of time in minutes and a kind — decision,
review, or hands-on work. When an offer is presented, its estimate
SHALL be available to the user alongside it.

#### Scenario: Presented offer shows its price
- **WHEN** an offer is presented to the user
- **THEN** the offer carries its estimated minutes and effort kind

### Requirement: Over-budget offers are deferred, visibly, and resurface
When an offer's estimated user-effort exceeds the user's remaining
declared attention budget, the arbiter SHALL defer the offer instead of
presenting it, SHALL record the deferral and its reason, and SHALL NOT
discard the offer. The deferral SHALL be visible in the control surface
and counted in the snapshot's open-commitments field. A deferred offer
SHALL be reconsidered when the budget frees up — at the start of a new
day, or when a major commitment reaches its end date — and SHALL still
pass every existing gate, including the daily offer cap, before being
presented. Timed offers and reminders whose moment falls inside a
declared unavailable window SHALL be scheduled outside that window.

#### Scenario: Over-budget offer deferred
- **WHEN** an offer's estimate exceeds the user's remaining budget for the day
- **THEN** the offer is not presented, is recorded as deferred with its reason, and remains visible as deferred

#### Scenario: Deferral is not loss
- **WHEN** a deferred offer exists and the user inspects open commitments
- **THEN** the deferred offer appears there, marked deferred

#### Scenario: Resurfacing when capacity frees
- **WHEN** a new day begins or a major commitment ends, freeing budget
- **THEN** deferred offers are reconsidered and may be presented, subject to all existing gates

#### Scenario: Unavailable window respected
- **WHEN** an offer's natural moment falls inside a declared unavailable window
- **THEN** it is scheduled outside the window

### Requirement: Plans state the user-effort they bill
A planner decomposing work SHALL prefer steps the system can complete
autonomously within its granted autonomy over steps that bill the
user's time, when both achieve the same step. For every step that does
bill the user, the plan SHALL state the expected user-effort — minutes
and kind — where the plan is presented.

#### Scenario: User-billed step is priced in the plan
- **WHEN** a plan containing a step only the user can perform is presented
- **THEN** that step is shown with its estimated minutes and effort kind

#### Scenario: Autonomous alternative preferred
- **WHEN** a step can be completed either by the system within its granted autonomy or by the user
- **THEN** the plan uses the system's completion and bills the user nothing for that step

### Requirement: Missing principal state falls back to existing behaviour
When principal state is absent or every principal field is stale,
consumers SHALL behave exactly as they did before this change: offers
are governed by the existing offer cap alone, plans carry no effort
accounting, and timing follows existing rules. No consumer SHALL block,
delay, or fail a turn, offer, or plan because principal state is
missing.

#### Scenario: No budget declared
- **WHEN** a user with no declared attention budget receives offers
- **THEN** the offers are governed by the existing daily cap and no other budget rule

#### Scenario: Turn proceeds without principal state
- **WHEN** a turn begins and no principal state exists for the user
- **THEN** the snapshot assembles normally, without a principal section, and consumers proceed

### Requirement: Principal state is per-user, inspectable, and editable
Principal state SHALL be stored per user with the same protections as
the memory stores, SHALL appear only in that user's snapshots, and
SHALL NOT be an input to another user's offers or plans. The user SHALL
be able to view every principal field as consumers see it and to edit
or clear each field; an edit SHALL take effect at the next assembly.

#### Scenario: User inspects and edits
- **WHEN** the user views the principal section and changes the attention budget
- **THEN** the next assembled snapshot shows the new budget with its new set-time

#### Scenario: No cross-user leakage
- **WHEN** snapshots are assembled for two different users
- **THEN** neither snapshot contains the other user's principal fields, and neither user's offers are shaped by the other's budget
