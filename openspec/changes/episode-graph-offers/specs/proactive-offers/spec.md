## ADDED Requirements

### Requirement: Offers are judged, not scheduled

The system SHALL decide whether to make a follow-up or timely offer with a judge that sees the candidate and its benefit reason, the user's recent outcomes for this kind and topic, the time since the last offer, and whether the user's last message looks like a short task command, and that returns `offer`, `hold` or `drop` with a benefit score, a style (`tell` or `ask`, with a short teaser for `ask`) and, for `hold`, a retry time. The system SHALL NOT apply a fixed cool-down, a per-thread limit or a fixed per-day count to follow-up offers. The system SHALL clamp a retry time to a sane range and SHALL record the judge's reason.

#### Scenario: Teaser or plain telling

- **WHEN** the judge returns `offer`
- **THEN** it also chooses `ask` with a teaser such as "Want to hear something interesting about tool calling?", or `tell` for low-stakes, plainly useful content

#### Scenario: Worth offering

- **WHEN** advice with a high benefit arrives and the user has accepted similar offers before
- **THEN** the judge returns `offer`

#### Scenario: Not worth interrupting

- **WHEN** advice with a marginal benefit arrives while the user is issuing short task commands
- **THEN** the judge returns `hold` with a later retry time, and nothing is said

#### Scenario: A nonsensical retry time

- **WHEN** the judge returns a retry time of zero or of years
- **THEN** the system clamps it into the allowed range

### Requirement: The benefit bar is learned from outcomes

The system SHALL keep a benefit bar per kind of offer and SHALL offer only when the judge's benefit score reaches the bar. The bar SHALL start at a moderate level, SHALL fall by a small bounded step when an offer is accepted, SHALL rise by a small bounded step when an offer is ignored, SHALL rise by a larger bounded step when an offer is declined, SHALL be unchanged by a deferral, SHALL drift back toward its starting value without new evidence, and SHALL stay within fixed limits. An explicit stop for a topic or kind SHALL create a permanent block, not a bar change.

#### Scenario: Acceptance makes Sutra bolder

- **WHEN** the user accepts several follow-up offers
- **THEN** the follow-up bar is lower than before, within its limits

#### Scenario: Declines make Sutra quieter

- **WHEN** the user declines several offers
- **THEN** the bar is higher, but never beyond its upper limit

#### Scenario: Old evidence fades

- **WHEN** weeks pass with no offers after a run of declines
- **THEN** the bar moves back toward its starting value

#### Scenario: Reset

- **WHEN** the user runs `/offers reset`
- **THEN** every bar returns to its starting value and blocks are kept

### Requirement: One arbiter lets one proactive item through

The system SHALL pass every proactive candidate (follow-up advice, timely signals, the interests nudge) through one arbiter that lets at most one item through per turn, none while an action is awaiting confirmation or another offer is open, and none that the user has blocked. The arbiter SHALL order candidates as urgent timely, then follow-up, then interests nudge. The interests nudge SHALL ask the arbiter for permission and SHALL keep its own existing limit as an additional guard. The arbiter SHALL enforce only these fixed rails: a daily maximum across all kinds (default 4, which urgent timely offers may use), a daily budget for this feature's own model calls, and the user's stops.

#### Scenario: One at a time

- **WHEN** a follow-up and an interests nudge are both possible on one turn
- **THEN** only the follow-up is offered

#### Scenario: Not during a confirmation

- **WHEN** an action is awaiting the user's confirmation
- **THEN** no offer is made

#### Scenario: A rail binds

- **WHEN** the daily maximum has been reached
- **THEN** a non-urgent candidate is held and an urgent one still goes through

#### Scenario: A blocked topic

- **WHEN** the user has stopped offers about a topic
- **THEN** no candidate on that topic passes the arbiter

### Requirement: A follow-up offer follows the answer and is a question

When the judge says `offer` for a follow-up, the system SHALL append the validated one-sentence question to the end of the finished reply, so that the user's own request is answered first, and SHALL record the appended words in the conversation history. The offer SHALL be counted as made only when it is appended. The system SHALL NOT append an offer to a confirmation question, an error reply, or a reply that delivers an accepted offer, and SHALL discard without counting a decision that was not said. The user's own request, including any tool calls, SHALL run normally.

#### Scenario: Answer first, then the offer

- **WHEN** a follow-up is chosen on a turn where the user asked for help naming a function
- **THEN** the reply answers that request and ends with a single question such as "Earlier you asked how tool calling works; want a quick example based on this?"

#### Scenario: The user's request is never replaced

- **WHEN** a follow-up is chosen on a turn that needs a tool
- **THEN** the tool runs normally and the offer is the last sentence of the reply

### Requirement: Timely offers come from signals and expire

The system SHALL accept signals with a kind, summary, source, urgency, expiry time and optional topic hint from any producer, and SHALL judge each against the graph neighbourhood retrieved for its summary and hint, deciding whether it matters to this user now. A signal connected to nothing the user has said or approved SHALL be judged on general importance only and held to a higher bar. The system SHALL drop an expired signal without speaking. Urgency SHALL be `low`, `medium` or `high`, with weather treated as `medium` by default. The system SHALL use the urgent path only for a `high` signal from a producer on an allowlist (default empty) with a short expiry, checked in code; all other signals take the ordinary path.

#### Scenario: A warning tied to a stated plan

- **WHEN** a snow warning arrives and the graph holds an episode where the user planned to drive in the mountains
- **THEN** the judge treats it as high benefit and the signal is offered

#### Scenario: An unrelated, ordinary signal

- **WHEN** a minor signal arrives that connects to nothing the user has said
- **THEN** it is judged against the higher general bar and is likely held or dropped

#### Scenario: Expired before a quiet moment

- **WHEN** a signal's expiry passes before it can be delivered
- **THEN** it is dropped and never spoken

#### Scenario: Urgency claimed by an unlisted producer

- **WHEN** a producer not on the allowlist marks a signal urgent
- **THEN** it takes the ordinary path

#### Scenario: Weather is medium by default

- **WHEN** a weather signal arrives with no explicit urgency
- **THEN** it is `medium` and is judged against the bar on the ordinary path

### Requirement: Offers are conversational and the judge picks the style

In a voice session the system SHALL deliver a timely offer at the next quiet moment through the existing notice mechanism, and in text SHALL hold it for the next reply. The judge SHALL choose between `tell`, one or two natural sentences stating the fact, and `ask`, one short teaser question whose wording fits the content. A safety-relevant alert SHALL be a `tell`. A `tell` SHALL NOT contain an action or a request for data, and an `ask` SHALL be one sentence. The system SHALL NOT require asking before telling, and SHALL NOT perform any action, spend or data change as part of an offer without the normal confirmation. A notice SHALL NOT interrupt a reply in progress.

#### Scenario: A plain heads-up

- **WHEN** a high-benefit, time-critical signal is ready and the user is silent
- **THEN** Sutra says it conversationally, such as "Heads up, snow is expected on the mountain road in about twenty minutes, so you may want to hold off on that drive."

#### Scenario: A teaser

- **WHEN** the judge picks `ask` for an interesting but non-urgent finding
- **THEN** Sutra says one sentence such as "Something good turned up for your Diwali plans, want to hear it?" and gives details only on yes

#### Scenario: Ignoring a tell costs nothing

- **WHEN** the user does not respond to a `tell`
- **THEN** nothing is repeated, and the outcome is recorded as `ignored`

#### Scenario: An offer never acts

- **WHEN** a signal suggests an action such as rerouting or rebooking
- **THEN** the offer only mentions it, and any action goes through the normal confirmation

### Requirement: The answer to an offer is soft

The system SHALL hold an open offer in a slot separate from the pending-action slot and SHALL clear it after one user turn whatever happens. On the next user turn, a phrase check for "not now", "later" and similar SHALL record `deferred`. Otherwise the intent classifier SHALL label the reply: affirm SHALL deliver; deny SHALL record `declined`; any other label, including a reply on another subject, SHALL record `ignored`, and the turn SHALL proceed as an ordinary message without asking again. Each outcome SHALL be stored with the offer's kind, topic and local hour and SHALL feed the bar.

#### Scenario: Yes

- **WHEN** the user answers "yes please"
- **THEN** the next step is delivered in that turn and the outcome is `accepted`

#### Scenario: Not now

- **WHEN** the user answers "not now"
- **THEN** the offer is deferred, the assistant says nothing more about it, and the bar is unchanged

#### Scenario: Off-topic reply

- **WHEN** the user ignores the offer and asks about something else
- **THEN** the outcome is `ignored`, the new request is answered normally, and the assistant does not ask whether that was a yes or a no

#### Scenario: No

- **WHEN** the user says "no thanks, I get it"
- **THEN** the outcome is `declined` and that node's open item is closed

#### Scenario: The offer does not linger

- **WHEN** the user's reply was unrelated and a later turn says "yes"
- **THEN** that yes is not treated as accepting the earlier offer

### Requirement: The example is grounded and short

On acceptance of a follow-up, the system SHALL instruct the assistant to give one short worked example of the stated step, built only from context present in the conversation or the approved interests, and to say so if it has to use a generic example. The assistant SHALL NOT state or invent facts about the user's projects that are not in its context. The example SHALL be in plain spoken sentences with code described in words and no markdown, and SHALL end with at most one question about going further.

#### Scenario: Grounded in current work

- **WHEN** the user accepts while building a small assistant that calls a weather function
- **THEN** the example uses that weather function as its subject

#### Scenario: No context available

- **WHEN** nothing in the conversation or approved interests gives a subject
- **THEN** the assistant uses a minimal generic example and says it is generic

#### Scenario: Progress is recorded

- **WHEN** the example has been delivered
- **THEN** the node's `example` item is marked done, and any further step is offered only if the judge finds it worth it

### Requirement: The user sees and controls everything

The system SHALL store offers, outcomes, signals, bars and blocks in an owner-only database separate from memory, interests and the graph. `/offers` SHALL show recent offers with outcome and the judge's reason, the current bars and any blocks. `/offers reset`, `/offers block|unblock <topic|kind>` and `/offers off|on` SHALL be provided. A `stop_offers` tool SHALL let the conversation model, on the user's request, block a topic or kind or turn offers off, and SHALL NOT be able to create, reopen or deliver an offer. `SUTRA_OFFERS=off` SHALL disable offers entirely, with no judge, advice or arbiter calls and no related tool.

#### Scenario: Voice stop

- **WHEN** the user says "stop offering me examples"
- **THEN** the model calls `stop_offers`, a block is recorded, and no such offers are made until it is lifted

#### Scenario: Seeing why

- **WHEN** the user runs `/offers`
- **THEN** each recent offer shows its kind, topic, outcome and the judge's reason

#### Scenario: Off

- **WHEN** `SUTRA_OFFERS=off`
- **THEN** no offer is made and no offer-related model call is made
