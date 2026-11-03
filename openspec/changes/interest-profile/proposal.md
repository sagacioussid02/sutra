## Why

Sutra records every conversation and extracts durable facts, but it has no idea what the user *cares about* as topics. That they asked about Halloween trips last month is exactly the signal that a Diwali outing nearby is worth raising, and today that connection only happens if the user asks. A small, inspectable interest profile, derived from what the user has said, is what later proactive behaviour (idle research, nudges) needs to read. Building it first, on its own, lets the user see and correct what Sutra thinks they like before anything acts on it.

## What Changes

- A new `interests` component with its own private database. It holds topics the user cares about, each with its evidence (the user's own words and when), a status, recency, and a history of how it changed.
- A **reflection pass** that reads the user's recent utterances (never replies, never tool results, and never turns that used financial tools) with a small model and *proposes* topics. Nothing it finds is used until the user approves it. Declined topics are never proposed again.
- **Changes are tracked, not overwritten.** Each reflection pass is shown the interests already known, so it can report that a topic is new, strengthened, or *changed* ("you used to ask about hiking trips, lately it's city breaks"). A change becomes a proposed revision with before and after; if approved, the old version is kept in the interest's history. An interest that goes quiet for a long time triggers one gentle check-in ("still into this?"). All of this is told to the user later, as a question, at a quiet moment.
- Approved interests appear to the conversation model as a short labelled block. When it fits, the assistant may connect a current topic to an interest ("you asked about Halloween trips; Diwali is coming up, want me to look up places?"), at most once per day, and any offer to look something up goes through the existing delegate-and-confirm flow.
- Full user control, in the existing style: list, why (show evidence), approve, reject, mute, add, forget one, forget all. Voice users get an ask-first spoken offer for each new proposal.
- Two switches: `SUTRA_INTERESTS=off` removes the feature entirely; `SUTRA_REFLECTION=off` stops automatic proposing but keeps manually added interests.

Facts the user states ("I get paid on the 15th") already have their own change tracking in the memory store (an updated fact supersedes the old one and says so). This change covers *topics and tastes*, and does not duplicate that.

Out of scope, deliberately: speaking up unprompted (that is `idle-research`, which must ask first), learning from corrections or which suggestions were accepted (`self-learning`), and any change to the memory database schema.

## Capabilities

### New Capabilities
- `interest-profile`: derived, user-approved interest topics with evidence, plus a capped in-conversation resurfacing behaviour.

### Modified Capabilities
(none)

## Impact

- New package `orchestrator/src/sutra_orchestrator/interests/` and a local `interests.db` (owner-only, gitignored), following the reminders and agents layout.
- `SqliteMemory` gains one read-only method to list recent user utterances with their tool names. No schema change.
- `Orchestrator` gains an optional interests provider that adds a prompt block each turn and a small local tool to mute an interest.
- Voice loop gains one more ask-first notice kind (a proposal waiting for a yes or no).
- One small-model call per day at most, over a bounded set of short utterances. The text of those utterances goes to Anthropic, as every turn already does.
- No gateway, twin, finanxe or minions changes.
- Depends on `assistant-memory` (episodes), `ephemeral-agents` (the follow-up offer), and `voice-background-tasks` (notices).
