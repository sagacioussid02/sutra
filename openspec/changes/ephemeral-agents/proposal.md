## Why

Some requests are bigger than one turn: "compare these three laptops for photo editing", "find out what changed in the new tax rules". Doing them inline blocks the conversation and burns the main context on intermediate material. The voice work already built the shape for this — `Orchestrator.fork()` lanes that run in the background and report back — but there is no deliberate, user-invoked delegation: a way to say "go research this and come back with an answer" and have a bounded worker do it.

**Status: stub — not implemented. This change is gated on the reminders + direct-answers changes (A+B) being dogfooded first, and on Sidd's explicit go-ahead.**

## What Changes (planned)

- A `delegate` capability: the user (or the main lane, with the user's knowledge) spawns an ephemeral subagent for a self-contained research or comparison task; its result returns as a proposal to the main conversation, announced through the ask-first notification path and filed in the inbox from the reminders change.
- Sandbox rules, enforced in code rather than by prompt: an ephemeral agent gets **no tools that mutate anything and no confirm-first (consequential) tools** — read-only lookups only; it **cannot spawn further agents**; it **cannot write memory** — anything it "learns" comes back as a proposal the main conversation (and the user) can accept or drop, never as a direct write; its **budget (turns, tool calls, wall-clock) is enforced by the harness**, like `max_tool_calls` today, not by asking the model to stop.
- Everything an ephemeral agent produces — including anything it read from the web — is treated as **untrusted data** by the main conversation: it can inform an answer, it cannot issue instructions, trigger tools, or confirm anything. This is the main prompt-injection surface in the whole roadmap, and the design must start from that.

## Capabilities

### New Capabilities

- `ephemeral-agents`: bounded, sandboxed, read-only delegation for research tasks, with results returned as proposals. (Stub — no spec yet; the spec is written when this change is picked up.)

## Impact

None yet — stub only. When picked up: expected to reuse `Orchestrator.fork()` and the background-lane notification queue, add a tool-surface filter for child lanes, and add budget plumbing. No gateway changes expected.
