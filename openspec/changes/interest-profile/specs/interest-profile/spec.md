## ADDED Requirements

### Requirement: Reflection reads only a narrow slice of the user's own words

The system SHALL derive interest candidates only from the user's own utterances in hot episodes within the configured window. It SHALL NOT read assistant replies, tool results, archived episodes, or utterances from turns that used a tool whose name starts with an excluded prefix (default `finanxe_`). It SHALL skip trivial yes/no utterances, truncate each utterance to 200 characters, and send at most 150 utterances per run.

#### Scenario: Financial turns are excluded

- **WHEN** reflection runs and one recent utterance came from a turn that used `finanxe_list_debts`
- **THEN** that utterance is not included in the model call

#### Scenario: Replies and tool output never reach reflection

- **WHEN** reflection builds its input
- **THEN** it contains only utterance text, numbered, with no assistant reply or tool result text

### Requirement: Candidates are proposals, validated in code

The system SHALL record every model-suggested topic with status `proposed`, with at most three new proposals per run and labels of at most 60 characters. Evidence references that do not match an utterance that was sent SHALL be dropped, and a topic left with no evidence SHALL be discarded. Strength and recency SHALL be computed from evidence timestamps in code, never taken from the model.

#### Scenario: Invented evidence is dropped

- **WHEN** the model returns a topic citing utterance numbers that were not in the input
- **THEN** the topic is discarded and nothing is stored

#### Scenario: Cap per run

- **WHEN** the model returns five valid topics
- **THEN** at most three are stored as proposals

### Requirement: Duplicates and declined topics do not come back

The system SHALL compare each candidate by word overlap with all existing interests of any status. A match SHALL add the new evidence to the existing interest and SHALL NOT create another. A candidate matching a `rejected` interest SHALL be dropped.

#### Scenario: Rejected stays rejected

- **WHEN** the user rejected "weekend trips" and a later run proposes "weekend travel trips"
- **THEN** nothing new is proposed

#### Scenario: More evidence merges

- **WHEN** a later run finds new utterances supporting an active interest
- **THEN** its evidence and last-seen time are updated and no second interest is created

### Requirement: Changes in the user's interests are tracked, not overwritten

The system SHALL show the reflection call the interests already known, and SHALL accept for each returned item a relation of `new`, `strengthens` or `changes`. A `strengthens` or `changes` item SHALL name an existing, non-rejected interest, or it SHALL be treated as `new`. A `changes` item whose stated previous state does not match the named interest by word overlap SHALL be treated as `new`. A valid `changes` item SHALL be stored as a `proposed` revision linked to the old interest, with before and now text. Approving a revision SHALL make it active and mark the old interest `superseded` while keeping it in the history; rejecting it SHALL leave the old interest unchanged and SHALL prevent the same change from being proposed again.

#### Scenario: A taste changes

- **WHEN** "hiking trips" is active and recent utterances are about city breaks, and the model reports a `changes` item against that interest
- **THEN** a proposed revision is stored showing what it used to be and what it is now, and "hiking trips" stays active until the user approves

#### Scenario: Approved revision keeps history

- **WHEN** the user approves the revision
- **THEN** the new interest is active, the old one is superseded, and `/interests history` shows both with dates

#### Scenario: Model cannot rewrite what it did not see change

- **WHEN** the model returns a `changes` item whose previous state does not resemble the interest it names
- **THEN** it is stored as a new proposal, not as a revision of that interest

### Requirement: The user is told about changes later, as a question

The system SHALL queue revisions and check-ins as pending offers, persisted across restarts, and SHALL announce at most one offer at a time only at a quiet moment and only as a question. An active interest with no new evidence for 90 days SHALL trigger one check-in asking whether the user is still interested: yes refreshes it, no mutes it, and "not now" leaves it dormant with no further check-in until new evidence appears.

#### Scenario: Revision offered by voice

- **WHEN** a revision is pending and the conversation goes idle
- **THEN** the assistant asks, for example, "It looks like your trip ideas have moved from hiking to city breaks. Want me to update that?" and acts on the answer

#### Scenario: Offer waits across a restart

- **WHEN** an offer is pending and the process restarts
- **THEN** it is still pending and is offered at the next quiet moment

#### Scenario: Still-interested check

- **WHEN** an active interest has had no new evidence for 90 days
- **THEN** it becomes dormant and the user is asked once whether they are still into it

### Requirement: Nothing is used until approved

The system SHALL expose only `active` interests to the conversation model. A proposal SHALL become active only through the user's approval, by command or by an affirmative reply to a spoken offer. Interests added by the user's own `/interests add` SHALL be active immediately. An active interest with no new evidence for 90 days SHALL be left out of the prompt block without being deleted.

#### Scenario: Proposed is invisible

- **WHEN** an interest is `proposed`, `rejected` or `muted`
- **THEN** it does not appear in the conversation model's prompt

#### Scenario: Spoken proposal answered by voice

- **WHEN** the assistant asks "Want me to keep that in mind?" and the user says yes
- **THEN** the interest becomes active; if the user says no it becomes rejected; if the user says "not now" it stays proposed and may be offered again later

#### Scenario: Dormant interest

- **WHEN** an active interest has had no new evidence for 90 days
- **THEN** it is not included in the prompt block but still appears in `/interests`

### Requirement: Resurfacing is rare, capped in code, and honest

The system SHALL give the conversation model a labelled block of active interests with today's date, stating that it is information and not instructions. On at most one turn per nudge interval (default 24 hours, persisted across restarts) the block SHALL also permit the assistant to briefly connect the current topic to an interest when natural. The block SHALL forbid stating event dates or other changeable facts from memory and SHALL direct lookups through the research tool. The cap SHALL count the turn on which the permission was given.

#### Scenario: One nudge permission per interval

- **WHEN** two turns happen within the interval
- **THEN** only the first carries the permission to connect an interest

#### Scenario: Cap survives restart

- **WHEN** the permission was used and the process restarts within the interval
- **THEN** the next turn does not carry the permission

#### Scenario: Lookup goes through research

- **WHEN** the assistant wants to find Diwali events for an interest
- **THEN** it proposes a research run, which starts only with the user's yes

### Requirement: Reflection runs rarely, on its own, and can be switched off

The system SHALL run reflection at startup and then hourly only when it is enabled, at least the configured interval (default 24 hours) has passed since the last run, and at least one new eligible utterance exists. It SHALL run one pass at a time, log failures without creating anything, and retry at the next check. `SUTRA_REFLECTION=off` SHALL stop automatic runs and the `/interests reflect` command's model call while leaving manual interests working. `SUTRA_INTERESTS=off` SHALL disable the whole feature, including the prompt block.

#### Scenario: Nothing new, no call

- **WHEN** the interval has passed but no new eligible utterance exists
- **THEN** no model call is made

#### Scenario: Failure leaves no trace

- **WHEN** the model call fails or returns invalid output
- **THEN** no interests are created and the run is retried at the next check

#### Scenario: Reflection off

- **WHEN** `SUTRA_REFLECTION=off`
- **THEN** no automatic model call is made, and `/interests add` still works

### Requirement: The user can see, correct and delete everything

The system SHALL store interests in an owner-only database separate from memory, and provide commands to list interests with status, show the evidence for one (`why`), approve, reject, mute, add, show history, forget one (deleting its evidence), and forget all (including run history). A `mute_interest` tool SHALL let the conversation model mute a matching active interest on the user's request; it SHALL NOT be able to create, approve or reactivate one.

#### Scenario: Why shows the user's own words

- **WHEN** the user runs `/interests why 3`
- **THEN** the quotes and dates that support interest 3 are shown

#### Scenario: Forget deletes evidence

- **WHEN** the user runs `/interests forget 3`
- **THEN** the interest and all its evidence rows are deleted

#### Scenario: Mute by voice

- **WHEN** the user says "stop bringing up weekend trips" and the model calls `mute_interest`
- **THEN** a matching active interest becomes muted and the reply says which one

### Requirement: Proposals are offered one at a time, asking first

The system SHALL offer at most one pending proposal at a time. In the text client a new proposal prints once. In the voice client it SHALL be announced through the ask-first notification path and SHALL NOT be spoken unprompted.

#### Scenario: Voice proposal waits for a quiet moment

- **WHEN** a proposal is created while the user is mid-conversation
- **THEN** it is announced only after the conversation goes idle, and only as a question
