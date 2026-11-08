## ADDED Requirements

### Requirement: Occasions are stored per user, from declared sources only
The system SHALL store occasions per user in a local, schema-versioned
store with the protections of the other per-user stores. An occasion
SHALL be created only from a user declaration, a user-confirmed entry,
or a pack the user has opted into. The system SHALL NOT create an
occasion from a calendar, from observed behaviour, or from inference
about the user.

#### Scenario: Declared occasion is stored
- **WHEN** the user declares an occasion with a name, a date rule, and a context line
- **THEN** the occasion is stored for that user with its source recorded

#### Scenario: Another user's occasions are invisible
- **WHEN** a snapshot or acknowledgment check runs for one user
- **THEN** only that user's occasions are considered

#### Scenario: Undeclared festival has no entry
- **WHEN** a festival occurs that the user has never declared or adopted from a pack
- **THEN** no occasion exists for it and nothing is acknowledged

### Requirement: Date rules evaluate exactly as declared
The system SHALL support three date rules: a single fixed date, an
annual recurrence by month and day, and a lunar entry carrying a
user-declared date for its next occurrence and a note naming the
calendar. The system SHALL NOT compute a lunar occurrence from tables
or external services. A lunar entry whose declared date has passed
SHALL be reported as needing its next date and SHALL NOT be treated
as occurring on any other date.

#### Scenario: Annual occasion recurs
- **WHEN** an annual occasion's month and day arrive in a later year
- **THEN** the occasion occurs again without being re-declared

#### Scenario: Lunar occasion uses its declared date
- **WHEN** the declared next-occurrence date of a lunar occasion arrives
- **THEN** the occasion occurs on that date

#### Scenario: Lapsed lunar entry is not guessed
- **WHEN** a lunar entry's declared date has passed and no new date has been declared
- **THEN** the entry shows as needing its next date and no acknowledgment is made for it

### Requirement: An occasion occurring today appears in world state
When an occasion occurs on the current day, the system SHALL expose
it as a field of the world-state snapshot, registered like any other
field, naming the occasions store as its source and carrying the
occasion's name and observance notes. When no occasion occurs, the
field SHALL be absent.

#### Scenario: Occasion in the snapshot
- **WHEN** a snapshot is assembled on a day an occasion occurs
- **THEN** the snapshot contains the occasion field with its source and the observance notes

#### Scenario: Ordinary day
- **WHEN** a snapshot is assembled on a day no occasion occurs
- **THEN** the snapshot has no occasion field

### Requirement: The acknowledgment is delivered at most once per occurrence
The system SHALL attach an acknowledgment to a reply only when an
occasion occurs that day and no acknowledgment for that occurrence
has been delivered. Delivery SHALL be recorded, keyed by occasion
and occurrence date, when the carrying reply is returned. A recorded
acknowledgment SHALL NOT be delivered again for that occurrence,
including after edits to the occasion.

#### Scenario: First interaction carries it, the second does not
- **WHEN** the user has two ordinary interactions on an occasion's day
- **THEN** the first reply carries the acknowledgment and the second does not

#### Scenario: Edited after delivery
- **WHEN** an occasion is edited after its acknowledgment was delivered that day
- **THEN** no second acknowledgment is delivered for that occurrence

### Requirement: The acknowledgment attaches to interaction; it never interrupts and is never late
The acknowledgment SHALL be attached to the first ordinary turn of
the occasion's day. It SHALL NOT be sent as a standalone message and
SHALL NOT initiate contact, spoken or otherwise. A turn consumed by a
pending confirmation SHALL NOT carry it; it waits for the next
ordinary turn the same day. If no ordinary interaction happens that
day, the acknowledgment SHALL NOT be delivered on a later day.

#### Scenario: No interaction that day
- **WHEN** an occasion occurs and the user does not interact that day
- **THEN** nothing is sent, and the following day begins with no carried-over acknowledgment

#### Scenario: Confirmation pending at first contact
- **WHEN** the day's first turn is a reply to a pending confirmation and a later ordinary turn follows
- **THEN** the acknowledgment is attached to the later ordinary turn, not to the confirmation reply

### Requirement: The acknowledgment carries no action and bypasses the arbiter
The acknowledgment SHALL NOT propose, book, schedule, remind, or
change any state beyond its own delivery record. It SHALL NOT enter
the offers store or the ask-first arbiter, SHALL NOT count against
the daily offer cap or the user's declared attention budget, and
SHALL NOT appear as an open commitment.

#### Scenario: Cap untouched
- **WHEN** an acknowledgment is delivered on a day when offers are also made
- **THEN** the day's offers are still governed by the full offer cap and budget, exactly as if no acknowledgment had occurred

#### Scenario: No side effects
- **WHEN** an acknowledgment is delivered
- **THEN** no reminder, offer, or commitment exists afterwards that did not exist before

### Requirement: Follow-on suggestions are ordinary offers
Any action suggested by an occasion — holding time, creating a
reminder, adjusting the day — SHALL be proposed through the normal
offer path, subject to the arbiter, the offer cap, and any effort
accounting, and SHALL take effect only on the user's acceptance
through the usual confirmation machinery.

#### Scenario: Keeping the evening clear is an offer
- **WHEN** an occasion's observance note suggests the evening should stay clear
- **THEN** Sutra may raise that as a separate offer, and declining it leaves the day exactly as it was

### Requirement: An observance never alters principal state silently
An occasion or its observance notes SHALL NOT create, edit, or extend
any principal-state field. Principal state SHALL change only when the
user confirms an edit through the paths `world-state` already
provides, including confirming an offer that proposes the edit.

#### Scenario: Puja in the evening
- **WHEN** an occasion with an "evening observance" note occurs and no edit is confirmed
- **THEN** the user's declared availability is unchanged in the next snapshot

### Requirement: Calendar packs are opt-in copies
A bundled calendar pack SHALL be inactive by default. Opting in SHALL
copy the pack's entries into the user's store as ordinary occasions
with the pack recorded as their source. Copied entries SHALL be
editable and deletable like declared ones, and no later pack change
SHALL add, restore, or modify a copied entry.

#### Scenario: Fresh install acknowledges nothing
- **WHEN** the system runs with packs available but none opted into
- **THEN** no pack occasion exists in the user's store

#### Scenario: Deleted pack entry stays deleted
- **WHEN** the user deletes an entry copied from a pack
- **THEN** the entry is gone and is not restored by any pack update

### Requirement: Occasions are inspectable and editable
The user SHALL be able to list, add, edit, remove, and — for lunar
entries — renew the occasions stored for them through the control
surface. An edit SHALL take effect at the next evaluation: an
occasion edited or removed before its day's first ordinary
interaction SHALL be acknowledged, or not, according to its edited
state.

#### Scenario: Removed before first interaction
- **WHEN** an occasion occurring today is removed before any ordinary interaction
- **THEN** no acknowledgment is delivered for it

#### Scenario: Edit before first interaction
- **WHEN** an occasion's context line is edited before the day's first ordinary interaction
- **THEN** the acknowledgment, when delivered, uses the edited entry
