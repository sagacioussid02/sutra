## ADDED Requirements

### Requirement: The bandit ranks only the rule-permitted set
Offer surfacing SHALL proceed in a fixed order: candidate offers are
filtered by the existing hard constraints (per-day and per-kind caps,
the block on offers while a confirmation is pending, quiet rules,
`self-learning` block effects, and declared capacity), and only then
may the bandit rank the surviving offers together with a
"surface nothing" choice. The bandit SHALL NOT surface, revive, or
reorder into eligibility any offer the constraints excluded, and SHALL
NOT modify any constraint.

#### Scenario: Bandit prefers an excluded offer
- **WHEN** an offer kind has hit its daily cap but the bandit's scores favour it
- **THEN** the offer is not surfaced; the bandit chooses only among the permitted offers or nothing

#### Scenario: Confirmation pending
- **WHEN** a confirmation is pending at the moment offers would be considered
- **THEN** no offer is surfaced and the bandit stage is not reached, exactly as before this change

### Requirement: Reward comes only from explicit user outcomes
The bandit SHALL update only from explicit offer outcomes recorded by
the user: accept (positive), defer (mildly positive, with its time
context), and dismiss (negative), using the fixed reward mapping
defined in code. It SHALL NOT infer reward from silence, dwell,
conversation length, or any other engagement signal. An offer that
expires unanswered SHALL be recorded as no-outcome and SHALL cause no
update.

#### Scenario: Offer ignored until it expires
- **WHEN** a surfaced offer expires without the user responding
- **THEN** the decision record shows no-outcome and the bandit's parameters are unchanged by it

#### Scenario: Offer deferred
- **WHEN** the user defers an offer
- **THEN** the outcome is recorded as a mild positive with its time context, not as a rejection

### Requirement: Context features are declared state only
Bandit context features SHALL be drawn only from the allowlist: offer
kind and source, effort estimate, time of day and day type, the user's
declared capacity and active commitments (principal-state /
`world-state` declared fields), and trailing outcome counts per kind.
Inferred personal attributes SHALL NOT be features. Bandits and their
outcome stores SHALL be per-user; one user's outcomes SHALL NOT affect
another user's ranking.

#### Scenario: Feature audit
- **WHEN** the feature builder runs for a decision
- **THEN** the recorded feature vector contains only allowlisted fields, and a test fails the suite if a non-allowlisted field appears

### Requirement: Cold start is current behaviour, activation is deliberate
Below the configured activation threshold of recorded outcomes, the
arbiter SHALL rank exactly as it did before this change while the
bandit logs shadow rankings. Activation SHALL require a deliberate
configuration step and SHALL be visible on the control surface together
with the outcome counts behind it. Disabling the bandit SHALL restore
rule-based ranking exactly, and deleting the outcomes store SHALL reset
the bandit to cold start.

#### Scenario: Below threshold
- **WHEN** offers are considered with fewer recorded outcomes than the threshold
- **THEN** the surfaced offer is the one the pre-existing rules would have chosen, and the bandit's shadow ranking is logged

#### Scenario: Bandit disabled after activation
- **WHEN** the bandit switch is turned off
- **THEN** ranking returns to the rule-based behaviour with no other change to the offers pipeline

### Requirement: Every bandit decision is explainable
Each ranking decision SHALL be logged with the permitted set, the
constraint outcomes that produced it, the feature vector, the arm
scores, the chosen arm, and the user outcome when it resolves. The
system SHALL be able to answer "why was I shown this?" from that log
in plain terms: the rules that allowed the offer, the context that
ranked it first, and the past outcomes that influenced the ranking.

#### Scenario: User asks why an offer appeared
- **WHEN** the user asks why a particular offer was shown
- **THEN** the answer is produced from that offer's decision record and names the permitting rules, the ranking context, and the influencing outcomes

### Requirement: Learning never reaches confirmations
The bandit SHALL rank offers only. It SHALL have no input to, and no
influence on, confirmations, reminder firing, or tool calls, all of
which remain governed by their existing deterministic and rule-based
mechanisms — the confirmation gate permanently rule-based with its
zero-false-affirm eval bar.

#### Scenario: Offer outcomes accumulate near a pending action
- **WHEN** offers are accepted or dismissed while unrelated confirmable actions exist in the system
- **THEN** those actions' confirmation behaviour is unchanged in every respect
