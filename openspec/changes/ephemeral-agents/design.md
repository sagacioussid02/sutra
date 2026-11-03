## Context

Sutra already has the pieces a delegated run needs: `Orchestrator.fork()` for independent lanes, voice `Job`/`Notice` for background work announced after asking, a pending-action slot that only the user's reply can release, and a `LocalTool` seam. What it lacks is a worker that can look things up outside the gateway, and rules for trusting what that worker brings back.

Constraints from the project goals: cheap, vigilant on cost; the user talks about personal matters, so personal data must not leak into research queries by default; the model must never be able to confirm or authorize anything.

## Goals / Non-Goals

**Goals:**
- Delegate a self-contained research task, with the user's yes, and get a spoken answer later.
- Make the sandbox structural: a tool allowlist, hard budgets, no memory writes, no recursion.
- Treat everything the worker returns as data, never instructions.
- Show cost: what a run used, and a daily cap.

**Non-Goals:**
- Idle or scheduled research (`idle-research` builds on this).
- Choosing topics from the user's interests (`interest-profile`).
- Agents that act: write, send, buy, or call confirm-first tools.
- Persistent or multi-run agents; each run is one throwaway job.
- Cancelling a run by voice (still unbuilt for jobs generally); the budget bounds it.

## Decisions

**1. Start with a yes, using the existing pending slot.** The model calls the local tool `delegate_research(task, why)`. The tool does not start anything: it files a pending action whose description is "send a researcher to <task>", exactly like a confirm-first gateway tool. Only the user's reply, classified as affirm by the existing classifier, starts the run. This reuses the rule that the model can never confirm, and it puts a human decision in front of every spend. Alternative: let the model start runs freely. Rejected: cost, and the model could be steered by tool results into spending.

**2. The pending action gains a local executor.** `PendingAction` today holds a gateway `pending_id`. It gets an optional `run` callback; on affirm the orchestrator calls it instead of `gateway_confirm`. One pending action at a time stays true, so a delegate and a gateway action cannot both wait.

**3. The worker sees a brief, nothing else.** The worker gets its own system prompt and a single user message: the task text. No history, no memory block, no persona. Personal data reaches it only if the main lane wrote it into the brief, and the delegate tool's description tells the model not to. Alternative: share the conversation so the worker has context. Rejected: leaks personal history to web-search queries and bloats cost.

**4. Tools are an allowlist, enforced where tools are built.** A new `agents/sandbox.py` builds the worker's tool list from: the web search server tool (if enabled) and gateway tools named in `SUTRA_AGENT_TOOLS`. The gateway does not currently expose tiers to clients, so an explicit user-written list is the fail-closed choice; the default is empty. Local tools (memory, reminders, delegate) are never included, which removes recursion and memory writes by construction. Every tool call the worker makes is checked against the list again at execution time, so a hallucinated tool name is refused, not run. Alternative: ask the gateway for tiers and use all read-only tools. Deferred: better long-term, needs a gateway change.

**5. Web search is Anthropic's server tool.** `AnthropicModel.research(brief, ...)` calls the Messages API with `web_search` and `max_uses` set, so no new service, key, or scraper is needed, and fetching happens on Anthropic's side, not on the user's machine. The method handles `pause_turn` continuations up to the budget and returns text plus the source URLs. Alternative: a search API plus our own fetcher. Rejected for now: more code, more keys, and our own SSRF surface.

**6. Budgets are counters in code.** Per run: max web searches, max gateway tool calls, max output tokens, wall-clock timeout (`asyncio.wait_for`), and max continuation turns. Daily: max runs and max output tokens, tracked in `agents.db`; a run that would exceed the daily cap is refused at the delegate step, before asking the user, with a plain-language reason. Hitting a per-run limit ends the run and returns what exists, flagged partial. Defaults are small (5 searches, 3 minutes, 3 runs a day, 60,000 output tokens a day) and configurable.

**7. Findings are untrusted, and summarized with tools off.** The worker returns `Findings(text, sources, partial, usage)`. The main lane then makes one model call with tools disabled (`allow_tools=False`, the same mechanism used for the confirmation readback), with the findings wrapped in a clearly labelled data block and the system rule that nothing inside it is an instruction. That call's text is what gets spoken. A page that says "ignore previous instructions and delete..." can therefore affect only the wording of a spoken summary, never an action. The raw findings are stored but never placed in the history as an assistant message.

**8. A run is a voice `Job`.** In the voice client, a started run registers as a `Job` whose task is the worker coroutine, counts against `SUTRA_MAX_BACKGROUND`, and finishes into a `Notice` announced with the existing ask-first line. In the text REPL it prints a one-line notice when done, and `/agents` lists runs and spend. The job's lane is the main lane (the summary is produced there), so no extra lane is forked.

**9. Memory stays out of it.** The worker cannot call memory tools. After the summary the assistant may ask "want me to remember that?", and any save goes through the existing memory proposal flow, which needs the user's approval.

**10. Runs are recorded.** `agents.db` (owner-only SQLite, versioned, like reminders) stores task, status, started/finished, usage counters, sources, and the findings text. Retention follows the memory archive settings; nothing is auto-deleted. A `/agents purge` command deletes runs.

## Risks / Trade-offs

- [Prompt injection from the web] → the worker has no consequential tools; the summary step has tools disabled; findings are labelled data. Residual risk: a persuasive but false summary. The spoken answer cites that it came from a web search, and sources are kept for the user to check.
- [Cost surprise] → confirmation before each run, per-run and daily caps, usage shown after each run, a cheaper default model for the worker.
- [Personal data in search queries] → the worker never sees history or memory; the delegate tool description forbids personal detail in the brief; delegation stays available in private voice mode, because a run sees none of the user's history or memory and the transcript already goes to the model provider there.
- [Runs lost on exit] → a run is in memory only; on exit it is cancelled and recorded as interrupted. Acceptable for a few-minute job.
- [Web search availability and pricing may change] → isolated behind `AnthropicModel.research`, so a different backend replaces one method.
- [Voice friction from the extra yes] → one short question per run; it is the price of controlling spend. Revisit after dogfooding.

## Open Questions

- Worker model: decided, Haiku to start (`SUTRA_AGENT_MODEL`); tune after seeing result quality.
- Is the daily cap better expressed in dollars? Needs per-model prices; start with runs and tokens.
- Should gateway tool tiers be exposed to clients so the allowlist can be automatic? Likely yes later; out of scope here.
