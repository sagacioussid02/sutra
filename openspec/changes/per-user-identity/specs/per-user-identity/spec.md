## ADDED Requirements

### Requirement: Every caller resolves to at most one user
The gateway SHALL resolve each authenticated caller's token to the user
id configured for that token, and SHALL pass that user id to adapters
that act on per-user data. A token with no configured mapping SHALL
resolve to no user.

#### Scenario: Mapped caller
- **WHEN** a caller whose token maps to user `alice` invokes a finanxe tool
- **THEN** the adapter calls finanxe with user id `alice`

#### Scenario: Two callers, two users
- **WHEN** callers mapped to different users invoke the same finanxe read tool in the same period
- **THEN** each call reaches finanxe under its own caller's user id

#### Scenario: Unmapped caller
- **WHEN** a caller whose token has no mapping invokes a tool that needs a user id
- **THEN** the call fails with an identity error and the upstream service is not called

### Requirement: No silent cross-user access
The system SHALL NOT substitute another user's id — including the
historical shared default `demo_user` — for a caller who has no mapping
or whose mapping does not cover a tool. The only exception SHALL be a
fallback explicitly configured for a single designated legacy token, and
every use of that fallback SHALL be recorded in the audit log as a
fallback.

#### Scenario: Legacy token uses the fallback
- **WHEN** the one designated legacy token invokes a finanxe tool before its mapping is configured
- **THEN** the call proceeds under the configured fallback id and the audit entry is marked as a fallback

#### Scenario: Non-legacy unmapped token
- **WHEN** any other unmapped token invokes a finanxe tool
- **THEN** the call fails closed and no fallback is applied

### Requirement: The effective user is audited on every call
Every audit entry for a tool call SHALL record the resolved user id the
call acted under, or that no user was resolved, in addition to the
existing caller identity.

#### Scenario: Confirm-first call audit
- **WHEN** a caller confirms and executes a side-effecting finanxe tool
- **THEN** the audit entry shows the user id whose data the call changed

### Requirement: Existing data is reached by mapping, not migration
The owner's existing finanxe data SHALL remain under its current id
(`demo_user`), and the owner's access to it SHALL be provided by an
explicit mapping entry for the owner's token.

#### Scenario: Owner after the change
- **WHEN** the owner's token, mapped to `demo_user`, invokes finanxe tools after this change ships
- **THEN** the owner sees the same data as before the change, and no other caller can reach that data without a mapping to the same id
