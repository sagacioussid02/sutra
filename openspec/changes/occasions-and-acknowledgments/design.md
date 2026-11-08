## Context

Sutra's sense of "now" comes from the world-state snapshot: presence,
calendar, open commitments, fresh events, and the principal state the
user has declared. None of it knows what a day *means* to this family.
The reminders machinery knows dates the user asked to be reminded
about; the episode graph knows what was discussed; the interest
profile knows topics the user likes. Occasions are none of those: a
standing, declared fact — "this day, every year, is Diwali here" —
plus the small social act of marking it.

The one design question that drives everything below is where that
act lives. Every proactive thing Sutra does today is an offer: judged,
capped, effort-priced, recorded as a commitment until answered. A
greeting fits none of that, and forcing it through would corrupt both
sides — offers would gain a member that ignores the rules, and the
greeting would gain a judge that can suppress it and a budget it can
exhaust.

## Goals / Non-Goals

**Goals:**
- Sutra marks the days this family observes, once, in passing, the
  way a person in the house would.
- Occasions are declared data with provenance, visible and editable
  by the user they describe, like principal state.
- The acknowledgment is mechanically guaranteed — once per
  occurrence, no action attached, no budget consumed — not left to
  the model's discretion.
- An occasion today is visible to every consumer through the
  world-state snapshot, with source and age like every other field.

**Non-Goals:**
- A reminder system for occasions. Nothing here schedules, alerts, or
  counts down; a reminder is a separate, ordinary artefact.
- Inferring occasions — from a calendar, from conversation topics,
  from the user's name or background. An undeclared festival is not
  acknowledged, full stop.
- Computing festival dates. Lunar and lunisolar dates come from the
  user's declaration, not from tables, astronomy, or a web service.
- Speaking unprompted. The acknowledgment never initiates contact; it
  rides on an interaction the user started.

## Decisions

### Acknowledgment is a category, not an offer
The pipeline gains a second kind of proactive content beside offers:
the acknowledgment. It is decided by code at turn start, rendered by
code (below), and recorded as delivered. It never enters the offers
store, never passes the arbiter or the judge, never counts against
the four-a-day cap or the principal attention budget, and never
appears in the snapshot's commitments field — it is not a commitment,
because it asks for nothing.

*Why:* the cap and the judge exist to protect the user from
proposals. A greeting is not a proposal; routing it through the
machinery built for proposals would let a busy day silently eat a
birthday, and would teach the offers store to hold items that are
never answered — the exact ambiguity the commitments field exists to
avoid.

*Alternative considered:* an offer with zero effort and auto-accept.
Rejected: zero is not the same as exempt — the judge could still
suppress it, deferral semantics would still apply, and "offers the
user never saw" would stop meaning one thing.

### Attachment at the first ordinary interaction
At turn start, alongside snapshot assembly, the pipeline asks the
occasions service whether an undelivered occasion occurs today. If
so, the acknowledgment is attached to that turn's reply and recorded
delivered, keyed by occasion and occurrence date. Two qualifications:

- A turn consumed by a pending confirmation does not carry it. The
  user is mid-decision; the greeting waits for the next ordinary turn
  the same day.
- Delivery is recorded when the reply is returned, not when the day
  rolls over. If the day passes with no ordinary interaction, nothing
  is recorded and nothing is owed: the acknowledgment is never
  delivered late, and the next occurrence is a fresh chance.

*Why:* "in passing" is the behaviour being specified. Attaching to
first contact makes the greeting part of a conversation the user
chose to have; making it a standalone message — spoken or pushed —
would turn a social grace into an interruption, and delivering it the
next morning would turn it into a report.

### Rendered by code, phrased within limits
Code renders the acknowledgment line from the entry itself — the
occasion's name and its context line ("Happy Diwali — puja this
evening, as you've noted") — and places it at the head of the reply.
The model is told, in the turn's context, that the acknowledgment has
been made, so it does not repeat or extend it into a proposal of its
own. What the occasion suggests *doing* is left to the normal
machinery: if a follow-on is worth proposing, it is proposed as an
offer, separately, where the user can decline it without declining
the day.

*Why:* once-ness, presence, and the no-action guarantee are
mechanical properties; only code can promise them. Letting the model
phrase the greeting from a prompt fact would make all three
probabilistic — mostly delivered, occasionally doubled, sometimes
grown into an unprompted plan.

### Date rules the user can actually state
Three rule kinds, matching how people state these days:

- **Once** — a single date (a wedding, a house closing).
- **Annual** — a month and day, recurring (birthdays, anniversaries,
  fixed-date festivals).
- **Lunar** — a note naming the calendar ("Hindu lunar calendar")
  plus the date of the next occurrence, declared by the user. When
  that date passes, the entry's state becomes *needs next date*:
  visible in the control surface, never acknowledged on a guessed
  date, and one command to renew when the user states the next one.

Lunar is deliberately not computed. Festival dates are exactly the
kind of fact this system refuses to derive quietly: a wrong computed
date acknowledges the wrong day with total confidence, while a
declared date that has run out fails visibly and asks. If a trusted
calendar source ever lands — most plausibly as an `inbound-events`
feed — it enters as a named source on the entry, separately approved,
not as a silent upgrade.

### Packs are copies, not subscriptions
A cultural calendar pack ships as static data in the repo. Opting in
copies its entries into the user's store as ordinary declared
entries, marked with the pack as their source. From that moment they
are the user's: editable, deletable, and never re-synced. Deleting a
pack entry is permanent; a later pack update never resurrects it,
because there is no sync to resurrect it through.

*Why:* subscription semantics would let a repo update silently add
acknowledgments the user never agreed to — declared-only in form,
inferred in effect. A copy keeps the provenance honest: the user
adopted these entries, on this date, and can un-adopt any of them.

### Occasions in world state, principal state untouched
The occasions service registers a snapshot field — occasions
occurring today, with names and observance notes — under the
world-state field registry, with its TTL at the end of the local day.
Consumers see it like any field: source attached, staleness rules
unchanged. Registration is all `world-state` needs from this change.

Observance notes do *not* flow into principal state. "Puja in the
evening" is a fact about the day, not a declaration that the user is
unavailable; evenings have contained both puja and questions before.
If the day should be shaped around an observance, that is an offer —
"shall I treat this evening as unavailable?" — and only a confirmed
yes writes principal state, through the control and editing path
`world-state` already defines. The acknowledgment path itself writes
nothing but its own delivery record.

### Per-user, inspectable, boring storage
The store follows the shape the repo already trusts — the `life` and
`offers` packages' layout (`db`, `store`, `service`, `commands`), a
schema-versioned local SQLite file at 0600, entries keyed by user.
Control commands join the existing command sets (the REPL's
`CommandSet` and any other surface's) beside the memory, offers, and
life commands: list, add, edit, remove, and renew a lunar entry. A
`SUTRA_OCCASIONS` switch, documented in `orchestrator/.env.example`,
turns the delivery check off without touching the store; with an
empty store the check is inert either way.

## Risks / Trade-offs

- [Greeting fatigue] → declared-only entries, at most once per
  occurrence, never a standalone message. A user who declares nothing
  hears nothing; a user who tires of an entry deletes it and it stays
  deleted.
- [A wrong lunar date] → the failure mode is visible, not silent: a
  passed lunar entry shows as *needs next date* and acknowledges
  nothing until renewed. The cost is one missed year, not a confident
  greeting on the wrong day.
- [Acknowledgment lands on a sombre first turn] → the user may open
  the day with bad news or an urgent problem. The line is one line,
  at the head, ignorable; code does not attempt sentiment analysis of
  the incoming turn to decide whether the day "deserves" marking —
  that judgement would misfire worse than the greeting.
- [Model repeats or extends the greeting] → the turn context states
  the acknowledgment was already made and that proposals belong to
  the offer path; a test pins that a delivered acknowledgment is
  absent from the following turn's context.
- [Pack contents age] → packs are copies taken at opt-in; stale pack
  data in the repo harms only future opt-ins, never existing users,
  and a pack refresh is a repo change like any other.

## Migration Plan

Nothing migrates: the store is new and starts empty. The delivery
check ships behind `SUTRA_OCCASIONS`; with no entries it costs one
store read per turn start. The world-state field registers only when
the switch is on, so a snapshot assembled with the change disabled is
byte-for-byte the old snapshot.

## Open Questions

- Should the acknowledgment line ever be model-phrased under a marked
  fact, for warmth? Design says code-rendered, for the guarantees;
  revisit only after dogfooding shows the rendered line feels stiff
  in real conversation.
- Do packs belong in this repo at all, or in user-provided files the
  store imports? Leaning in-repo for the one or two packs the owner
  actually wants, import as a later convenience — both end at the
  same copied entries.
