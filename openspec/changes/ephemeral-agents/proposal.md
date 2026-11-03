## Why

Some requests are bigger than one turn: "compare these three laptops for photo editing", "find out what changed in the new tax rules", "where could I go for Diwali this year?". Doing them inline blocks the conversation and fills the main context with intermediate material. The voice work already built the shape for this (`Orchestrator.fork()` lanes that run in the background and report back through an ask-first announcement), but there is no deliberate way to say "go research this and come back with an answer" and have a bounded worker do it.

It is also the first place untrusted content (web pages) enters the system on purpose, so the safety rules have to be settled before the feature exists, not after.

## What Changes

- Add a `delegate_research` capability: when a request needs research, the assistant proposes sending a researcher ("I can send someone to look into that. It'll take a few minutes. Want me to?"). The user's yes starts it. A delegated run is a background job like any other: the conversation carries on, and the result is announced through the existing ask-first path.
- An ephemeral agent is a throwaway worker with a **brief** (the task, written by the main lane) and nothing else: no conversation history, no memory, no personal data unless the brief contains it.
- Its tools are an explicit allowlist: Anthropic's server-side web search, plus any gateway tools the user names in `SUTRA_AGENT_TOOLS` (default: none). Nothing that mutates, nothing confirm-first, no local tools, no `delegate_research`. Enforced in code.
- Budgets are enforced by the harness, not the prompt: tool calls, searches, output tokens, wall-clock, and a daily cap on runs. Hitting any limit ends the run with whatever it has, marked partial.
- The result comes back as **untrusted findings** (text and source URLs). The main lane turns them into a short spoken summary in a step with tools disabled, so anything injected in a web page cannot trigger an action. The agent cannot write memory; at most the summary offers "want me to remember that?".
- Runs are recorded locally (task, status, cost counters, result) so the user can list them and see what was spent.

## Capabilities

### New Capabilities
- `ephemeral-agents`: bounded, sandboxed, read-only delegation for research tasks, started with the user's yes and returning untrusted findings through the ask-first path.

### Modified Capabilities
(none; `voice-background-tasks` gains one more kind of job but its requirements are unchanged)

## Impact

- New package `orchestrator/src/sutra_orchestrator/agents/` and a local `agents.db` (private, gitignored), following the `reminders` package layout.
- `AnthropicModel` gains a research call that uses the web search server tool. This is the first outbound web access in the system; the task text and search queries go to Anthropic.
- `Orchestrator` gains a local `delegate_research` tool and a way for a pending action to be a local run instead of a gateway call.
- Voice loop: a delegated run registers as a `Job` and shares the existing cap of two background jobs.
- New settings: `SUTRA_AGENTS`, `SUTRA_AGENT_MODEL`, `SUTRA_AGENT_TOOLS`, per-run and daily budgets. Cost is real; defaults are small.
- No gateway, twin, finanxe or minions changes.
- Depends on `voice-background-tasks` (jobs, notices) and `reminders-scheduler`/`direct-answers` (merged).
