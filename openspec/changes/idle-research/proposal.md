## Why

Sutra knows what the user is into (approved interests) and what they have been planning (the episode graph), and it can run bounded, sandboxed research and decide when something is worth saying. Nothing connects them: if the user wants to know what's on this Diwali, they have to ask. When the user is away, a small, strictly budgeted piece of research on something they care about can leave something genuinely useful ready, which Sutra then offers in a conversational way and only when the offer system judges it worth the interruption.

## What Changes

- **An idle researcher.** A background task that, when the user has been quiet for a while and nothing is running or awaiting confirmation, picks at most one topic to look into, runs one ephemeral research run on it, and files the result as a *signal* for the offers system. It is **off by default** and turned on by the user.
- **A picker, not a script.** A small tools-off model call sees only the user's approved interests and the topics of recent plans from the graph (never their gists), today's date, and what was researched before, and returns a topic, a self-contained brief and a value score, or nothing. Code checks the brief for anything personal. The score has to clear a learned bar that moves with how the user reacts to findings.
- **Findings are untrusted data.** The result is summarised by a tools-off call into a few sentences, dated "as of", and carried as a signal that expires in a few days. It is never written to memory, and it is never spoken verbatim without the user saying yes.
- **Delivered by the existing offers system.** The signal is judged like any other (benefit against the bar, connection to the graph, one at a time, daily rails) and is always put as a teaser question. Yes gives the summary; "not now" holds it; "no" closes it and teaches the bar.
- **Hard rails.** Idle runs have their own small daily cap and a minimum gap between runs, always leave room for the user's own requests, stop cold when spent, and never run while the user is talking. Failures back off.
- **Control.** `/idle` shows status, today's use and what was researched; `/idle on|off|now|forget`; "stop telling me about X" already blocks a topic for research too.

Out of scope: producing weather or calendar signals (their own producers later), research on anything that is not an approved interest or a recent plan, and any action taken on findings.

## Capabilities

### New Capabilities
- `idle-research`: budgeted background research over approved interests and recent plans, delivered as judged, asked-first offers.

### Modified Capabilities
(none)

## Impact

- New package `orchestrator/src/sutra_orchestrator/idle/` and a small local `idle.db` (owner-only, gitignored).
- `OffersService` gains one rule (a `research` signal is always an ask) and a hook that lets the researcher's own bar learn from the outcome of its findings. `Orchestrator` gains a last-activity time. No schema changes to existing databases.
- Web access happens only through the existing research worker and its limits; the topic brief is the only thing that leaves the machine.
- Depends on `interest-profile`, `ephemeral-agents`, and `episode-graph-offers`.
