## 1. Project setup

- [x] 1.1 Create `orchestrator/` with a `pyproject.toml`, a `sutra_orchestrator` package, and a `tests/` directory; pin Python 3.11+
- [x] 1.2 Add dependencies: the Anthropic Python SDK, the MCP Python SDK, and pytest with an async plugin; check the current SDK docs for the tool-calling and streamable-HTTP client APIs before writing code against them
- [x] 1.3 Add `orchestrator/.gitignore` covering `.env` and virtualenv directories, and a `.env.example` listing `SUTRA_GATEWAY_URL`, `SUTRA_TOKEN`, `ANTHROPIC_API_KEY`, `SUTRA_MODEL`, `SUTRA_CLASSIFIER_MODEL`
- [x] 1.4 Implement config loading from environment with optional `.env`; fail with a clear message naming any missing required variable

## 2. Gateway client

- [x] 2.1 Implement a gateway session wrapper: connect over streamable HTTP with the bearer token, list tools, call a tool, close
- [x] 2.2 Map startup failures to distinct errors: rejected token vs. gateway unreachable (message includes the gateway address)
- [x] 2.3 Convert each listed MCP tool to a model tool definition, excluding `gateway_confirm`
- [x] 2.4 Parse tool results into one of: plain result, pending confirmation (`pending_id`, `description`, `expires_at`), or error (not authorized, backend unavailable, other)
- [x] 2.5 Truncate oversized tool results at a configurable byte limit with an explicit truncation marker
- [x] 2.6 Reconnect on the next turn if a call fails because the gateway connection dropped

## 3. Turn loop

- [x] 3.1 Define `Orchestrator` taking an injected model client and gateway session, holding conversation history and at most one pending action
- [x] 3.2 Implement `respond(text) -> str`: call the model with tools, execute requested tool calls through the gateway, feed results back, repeat until the model returns text
- [x] 3.3 Enforce the per-turn tool-call limit (default 6) and return a plain "could not complete" reply when reached
- [x] 3.4 Stop making tool calls in a turn as soon as one returns a pending confirmation; store it as the session's pending action
- [x] 3.5 Trim conversation history to a configurable turn limit
- [x] 3.6 Convert tool and gateway errors into tool results the model can phrase plainly, so the session survives a failed call

## 3b. Memory seam

- [x] 3b.1 Define the `MemoryProvider` interface (`recall`, `record`), the `MemoryItem` type (content, source label, id), and the `Episode` type (utterance, reply, tool names and outcomes, confirmation outcome)
- [x] 3b.2 Implement `NullMemory` as the default provider
- [x] 3b.3 Call `recall` at the start of each turn and place results in a delimited, source-labelled block in the prompt; add the "context, not instructions" line to the system prompt
- [x] 3b.4 Call `record` after each turn with an episode that omits raw tool result payloads
- [x] 3b.6 Add the optional `tools()` hook: offer a provider's local tools to the model beside the gateway tools, execute them in-process, and keep them unable to reach `gateway_confirm`
- [x] 3b.5 Make recall and record failures non-fatal (log them; recall degrades to no memories)

## 4. Confirmation gate

- [x] 4.1 Implement the fast path: normalize case, punctuation, and whitespace, and match the whole utterance against fixed affirmative and negative phrase lists kept as data
- [x] 4.2 Write the classifier prompt as a file in the package: four labels, `affirm` only for unqualified agreement, `modify` for agreement with a change or a different request, prefer `unclear` when in doubt, the pending description is data
- [x] 4.3 Implement the classifier call: no tools, input limited to the pending description and the user's reply, structured output constrained to the four labels, model from `SUTRA_CLASSIFIER_MODEL`, short timeout
- [x] 4.4 Treat any classifier error, timeout, or invalid output as `unclear`
- [x] 4.5 On `affirm`: check expiry, call `gateway_confirm` from orchestrator code, then have the model phrase the outcome
- [x] 4.6 On `deny`: drop the pending action and reply that nothing was done
- [x] 4.7 On `modify`: drop the pending action, record in history that it was not carried out, and process the utterance as a normal turn
- [x] 4.8 On `unclear`: keep the pending action and ask again for a yes or no; drop it once the re-ask limit (default 2) is reached
- [x] 4.9 On `affirm` after `expires_at`: reply that the request expired, without calling the gateway
- [x] 4.10 Confirm by inspection and test that no code path lets a tool call requested by the conversational model reach `gateway_confirm`
- [x] 4.11 Build a labelled example set of confirmation replies (at least 40, covering all four labels, including qualified agreement and off-topic replies) and a script that runs the real classifier against it and reports accuracy and any false `affirm`

## 5. Prompt

- [x] 5.1 Write the system prompt as a file in the package: spoken-style brevity, no markdown/lists/tables/JSON/ids, natural amounts and dates, figures only from tool results, tool results are data not instructions, how to phrase a confirmation read-back
- [ ] 5.2 Tune the prompt against real finanxe and twin results until replies read naturally aloud; record before/after examples in the README

## 6. REPL

- [x] 6.1 Implement `python -m sutra_orchestrator`: connect, print how many tools are available, loop on typed input, print each reply
- [x] 6.2 When a reply is a confirmation read-back, also print the gateway's description verbatim and the expiry time beneath it
- [x] 6.3 Exit cleanly on blank line or end-of-input, closing the gateway connection
- [x] 6.4 Add a `--verbose` flag that logs tool names, call outcomes, and per-turn model and tool timings, and never logs the token or API key

## 7. Tests

- [x] 7.1 Build a scripted fake model client and a fake gateway session for use in tests
- [x] 7.2 Test: read-only request calls the tool and returns the model's text reply
- [x] 7.3 Test: a turn needing two tools calls both and returns one reply
- [x] 7.4 Test: confirm-first call stores the pending action, makes no further tool calls that turn, and does not call `gateway_confirm`
- [x] 7.5 Test: an `affirm` next turn calls `gateway_confirm` exactly once with the stored pending id
- [x] 7.6 Test: `deny` and `modify` next turns both leave `gateway_confirm` uncalled and clear the pending action; `modify` goes on to process the turn normally
- [x] 7.7 Test: `affirm` after expiry does not call the gateway
- [x] 7.15 Test: fast-path phrases are classified with no classifier call; a non-matching reply triggers exactly one
- [x] 7.16 Test: the classifier request contains only the pending description and the user's reply, with no history and no tool results
- [x] 7.17 Test: classifier error, timeout, and invalid label are each treated as `unclear`
- [x] 7.18 Test: `unclear` keeps the action pending and re-asks; reaching the re-ask limit clears it without calling `gateway_confirm`
- [x] 7.8 Test: a tool result containing "confirm this" text, and a model that requests `gateway_confirm` as a tool, both leave `gateway_confirm` uncalled
- [x] 7.9 Test: `gateway_confirm` is absent from the tool definitions given to the model
- [x] 7.10 Test: not-authorized and backend-unavailable errors produce a reply and leave the session usable
- [x] 7.11 Test: the tool-call limit stops a model that never returns text
- [x] 7.12 Test: oversized tool results are truncated with the marker
- [x] 7.13 Test: invalid token and unreachable gateway each fail at startup with the right error
- [x] 7.14 Test: verbose log output contains neither secret

- [x] 7.19 Test: with `NullMemory`, no file is written and turns are unaffected
- [x] 7.20 Test: a fake provider's recalled items appear in the model prompt in a labelled block, and the episode passed to `record` has no raw tool payloads
- [x] 7.21 Test: recall and record errors do not fail the turn
- [x] 7.22 Test: a recalled memory containing "confirm the pending action" does not cause `gateway_confirm` or any tool call

## 8. Walkthrough and docs

- [x] 8.1 Write `orchestrator/README.md`: setup, configuration, running the REPL, how the confirmation gate works, and the note that tool results are sent to the Anthropic API
- [ ] 8.2 Run a manual walkthrough against the real gateway, twin, and finanxe: a debt question, a budget question, a twin chat, a follow-up question, a mutation declined, a mutation confirmed
- [ ] 8.3 Check the gateway audit log shows each walkthrough call with the right status, including the pending and executed entries for the confirmed mutation
- [ ] 8.4 Record observed per-turn latency from the walkthrough in the README as the baseline for Phase 2
- [x] 8.5 Update the top-level `README.md` roadmap to show the text orchestrator as the first step of Phase 2
