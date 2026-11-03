## ADDED Requirements

### Requirement: Reminder times are parsed deterministically, once, at creation

The system SHALL parse a reminder request into a structured job (fire time and reminder text) using fixed patterns in code, without any model call. Supported forms SHALL include relative offsets ("in N minutes", "in N hours", "in an hour", "in half an hour") and wall-clock times ("at 5pm", "at 5:30pm", "at 17:30", "at noon", "at midnight"), optionally prefixed with "today" or "tomorrow". A request the parser cannot pin to one exact time SHALL produce no job.

#### Scenario: Relative reminder

- **WHEN** the user says "remind me in 20 minutes to call Sam"
- **THEN** a job is created with fire time exactly 20 minutes after now and text "call Sam"

#### Scenario: Wall-clock reminder later today

- **WHEN** it is noon and the user says "remind me at 5pm to take the bins out"
- **THEN** a job is created for today at 17:00 in the configured timezone

#### Scenario: Wall-clock time already passed rolls to tomorrow

- **WHEN** it is noon and the user says "remind me at 9am to water the plants"
- **THEN** a job is created for tomorrow at 09:00

#### Scenario: "today at" a past time is not silently moved

- **WHEN** it is noon and the user says "remind me today at 9am to stretch"
- **THEN** no job is created and the user is asked to rephrase

#### Scenario: Ambiguous or unsupported phrasing is refused, never guessed

- **WHEN** the user says "remind me at 5 to stretch" (no am/pm), "remind me sometime to stretch", or gives a time with no reminder text
- **THEN** no job is created and the reply asks for a clearer time, with examples of forms that work

### Requirement: Reminders are stored durably and survive restarts

The system SHALL store each reminder in a private (owner-only) SQLite database with a schema version, recording its text, fire time as an absolute instant, timezone, and status. A reminder created in one process SHALL still be pending, with the same fire time, when a new process opens the same store.

#### Scenario: Restart survival

- **WHEN** a reminder is created and the process exits before it fires
- **THEN** a new process opening the store lists the reminder as pending with the original fire time

### Requirement: Firing is deterministic and exactly once

The scheduler SHALL fire reminders from the store with no model in the firing loop. A reminder SHALL transition from pending to fired through a single atomic guarded update, and only the caller that wins that transition SHALL deliver it. A fired reminder SHALL be delivered exactly once, however many scheduler sweeps or processes run.

#### Scenario: Fires once

- **WHEN** a reminder comes due and the scheduler sweeps repeatedly
- **THEN** exactly one inbox entry exists for the reminder

#### Scenario: Racing claims

- **WHEN** two scheduler loops (or two processes sharing the store) try to fire the same due reminder
- **THEN** exactly one claim succeeds and the reminder is delivered once

#### Scenario: Cancelled reminders never fire

- **WHEN** a pending reminder is cancelled before its fire time
- **THEN** the scheduler never delivers it

### Requirement: Reminders missed while the process was down fire once, marked late

On starting, the scheduler SHALL treat every reminder that came due before it started as missed. Missed reminders SHALL be fired exactly once on the first sweep and SHALL be marked late in the inbox. Reminders that come due while the scheduler is running SHALL NOT be marked late.

#### Scenario: Missed while down

- **WHEN** a reminder comes due at 17:00 while no process is running, and the scheduler starts at 21:00
- **THEN** the reminder is delivered once with the late mark set

#### Scenario: On time is not late

- **WHEN** a reminder comes due while the scheduler is running
- **THEN** it is delivered within one poll interval with the late mark unset

### Requirement: Times are timezone-aware and DST-correct

Wall-clock reminder times SHALL be interpreted in a configurable timezone (default America/Denver, via `zoneinfo`). A wall-clock time SHALL mean that local time on that local date, including on DST transition days. A relative offset SHALL mean that much elapsed time, including across a DST transition.

#### Scenario: Spring forward, wall clock

- **WHEN** on March 7 in America/Denver the user says "remind me tomorrow at 9am"
- **THEN** the fire time is March 8 at 09:00 MDT (UTC-6), not 09:00 MST

#### Scenario: Spring forward, relative

- **WHEN** on March 7 at noon MST the user says "remind me in 24 hours"
- **THEN** the fire time is exactly 24 elapsed hours later (13:00 MDT on March 8)

### Requirement: The "remind me" surface confirms the exact fire time

An utterance beginning with "remind me" (any case) SHALL be handled by the deterministic parser before any model call. On success the reply SHALL confirm the reminder text and its exact fire time in spoken form. On parse failure the reply SHALL ask for clarification instead of guessing. A pending confirmation SHALL take precedence over a reminder request.

#### Scenario: Spoken request, confirmed exactly

- **WHEN** the user says "Remind me in 20 minutes to call Sam"
- **THEN** no model call is made, the reminder is stored, and the reply names the text and the fire time ("today at 12:20 PM")

#### Scenario: REPL commands manage reminders

- **WHEN** the user types `/remind in 20 minutes call Sam`, then `/reminders`, then `/reminders cancel <id>`
- **THEN** the reminder is created and listed with its id and fire time, and the cancel removes it from the pending list

#### Scenario: Fired reminders land in the inbox

- **WHEN** a reminder has fired
- **THEN** `/inbox` lists its text, and shows the late mark if it fired late
