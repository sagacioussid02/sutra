## 1. Sandbox and budgets

- [x] 1.1 Add `agents/` package: `Budget` (per-run and daily limits, loaded from config), `Findings` dataclass, `Sandbox` that builds the allowlisted tool list and refuses anything else at execution time
- [x] 1.2 Config (README only; `.env.example` not touched): `SUTRA_AGENTS`, `SUTRA_AGENT_MODEL`, `SUTRA_AGENT_TOOLS`, per-run and daily limits; defaults small; document in README and `.env.example`
- [x] 1.3 Tests: allowlist refuses local tools, `delegate_research`, `gateway_confirm`, and unlisted gateway tools; a held (pending) gateway result is discarded unconfirmed

## 2. Worker

- [x] 2.1 `AnthropicModel.research(brief, ...)` using the web search server tool with `max_uses`, handling `pause_turn` up to the turn budget; returns text, sources, usage
- [x] 2.2 Worker loop in `agents/worker.py`: brief-only prompt, allowlisted gateway calls, counters for tool calls, tokens and wall-clock (`asyncio.wait_for`); returns partial findings on any limit
- [x] 2.3 Tests with a scripted model: limits end the run with partial findings; no history or memory in the model call

## 3. Storage

- [x] 3.1 `agents/db.py` and `store.py`: owner-only versioned SQLite for runs and daily usage; interrupted status on shutdown
- [x] 3.2 Tests: persistence across restart, file mode, daily usage accumulation

## 4. Delegation in the orchestrator

- [x] 4.1 Local tool `delegate_research(task, why)` that checks the daily cap, then files a pending action with a local `run` executor (no run started)
- [x] 4.2 `PendingAction` gains the optional executor; affirm runs it, deny and expiry discard it; one pending action at a time still holds
- [x] 4.3 Summary step: one tools-disabled model call over labelled findings; findings never enter history as an assistant message
- [x] 4.4 Tests: model cannot start a run; yes starts it; no does not; second pending skipped; injected instructions in findings cause no tool call

## 5. Clients

- [x] 5.1 Voice: a started run registers as a `Job`, shares the background cap, and finishes into the ask-first notice (delegation also works in private mode)
- [x] 5.2 Text REPL: one-line notice on completion; `/agents` lists runs and usage, `/agents purge` deletes them
- [x] 5.3 Tests for the voice job path and the REPL commands

## 6. Docs and verification

- [x] 6.1 README section: what it does, what it sends where, budgets, how to turn it off
- [ ] 6.2 Manual check with a real key: a small research request end to end, cost shown, partial result on a tight limit
- [ ] 6.3 Update the roadmap in the top-level README
