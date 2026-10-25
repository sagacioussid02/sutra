# Sutra text orchestrator

A text-in, text-out assistant that talks to the Sutra gateway. You type a
request in plain language; a Claude model picks the right gateway tools,
calls them, and answers in short spoken-style sentences. It is the brain that
Phase 2's voice pipeline will wrap with speech-to-text and text-to-speech.

```
you> how much debt do I have?
sutra> You have three debts, about twelve thousand dollars in total. The
biggest is your Chase card at about four thousand.
```

## Setup

Python 3.11+ and a running gateway (see the top-level README).

```sh
cd orchestrator
uv venv --python 3.11 .venv && uv pip install -e ".[dev]"
cp .env.example .env     # then fill it in
```

| Variable | Meaning |
|---|---|
| `SUTRA_TOKEN` | Your bearer token: the `token:` value for your user in `gateway/tokens.yaml`. Required. |
| `ANTHROPIC_API_KEY` | Required. |
| `SUTRA_GATEWAY_URL` | Default `http://127.0.0.1:8765`. |
| `SUTRA_MODEL` | The conversational model. Default `claude-sonnet-5-5`. |
| `SUTRA_CLASSIFIER_MODEL` | Small model that reads yes/no replies. Default `claude-haiku-5-5`. |
| `SUTRA_MAX_TOOL_CALLS` | Tool calls allowed per turn. Default 6. |
| `SUTRA_HISTORY_TURNS` | Conversation turns kept in the session. Default 20. |
| `SUTRA_MAX_RESULT_BYTES` | Tool results larger than this are truncated. Default 16000. |
| `SUTRA_REASK_LIMIT` | Times an unclear reply to a confirmation is re-asked. Default 2. |
| `SUTRA_MEMORY` | `on` (default) or `off`. Off runs with no memory at all. |
| `SUTRA_MEMORY_DIR` | Where the memory databases live. Default `orchestrator/data`. |
| `SUTRA_EXTRACTOR_MODEL` | Small model that extracts what you tell it about yourself. Default `claude-haiku-5-5`. |
| `SUTRA_RECORD_REPLIES` | `on` (default) or `off`. Whether the assistant's reply text is kept in the conversation log. |
| `SUTRA_EPISODE_HOT_DAYS` | Conversations older than this are moved to the archive. Default 30. |

Real environment variables win over `.env`. `.env` is gitignored. Neither the
token nor the API key is ever logged or put in model context.

## Run

```sh
.venv/bin/python -m sutra_orchestrator            # talk
.venv/bin/python -m sutra_orchestrator --verbose  # also log tool calls and timings
```

A blank line (or Ctrl-D) quits. The tools you can reach are exactly the ones
the gateway lists for your token (`allowed_tools` in `tokens.yaml`), so a tool
you approve in `sutra-discover` and add to `allowed_tools` shows up here with
no change to this code.

## How an action that changes things works

Some gateway tools change your data (`confirm-first` tools). Calling one does
not run it: the gateway holds it and returns a description. Then:

1. The assistant reads back what will happen and asks for a yes or no. The
   REPL also prints the gateway's own description and expiry underneath, so
   you can check the assistant's paraphrase against it.
2. Your next message is classified as one of four things:
   - **affirm**: "yes", "sure, sounds good", "go for it". The action runs.
   - **deny**: "no", "nah, hold off". Nothing runs.
   - **modify**: "yes, but make it two hundred", or any other request. Nothing
     runs; the held action is dropped and your message is handled as a new
     request (a changed action comes back as a new confirmation).
   - **unclear**: "hmm", "I guess". The action stays held and you are asked
     again, up to the re-ask limit, then it is dropped.
3. Plain replies like "yes" and "cancel" are matched in code, with no model
   call. Everything else goes to a separate small classifier model that sees
   only the gateway's description and your reply, never the conversation or
   any tool results. A classifier failure counts as unclear, never as a yes.

**The conversational model can never confirm an action.** `gateway_confirm`
is not in the tool list it is given, a request for it is refused, and the
only code that calls it runs after your own reply was classified `affirm`.
This holds even if a tool result or a remembered note says "the user has
confirmed": text from tools is data, and nothing the model reads can approve
an action.

## What leaves your machine

Tool results, including finanxe financial data, and your messages are sent to
the Anthropic API as model context. finanxe's own agent already sends its data
there; this is new for the gateway path and for twin data. Results over
`SUTRA_MAX_RESULT_BYTES` are truncated first. With memory on, each of your
messages is also sent to the small extractor model, which sees only what you
wrote (never tool results or the assistant's replies).

## Memory

The assistant remembers what you tell it, across sessions, in a local database
you can read, correct, and erase. Memory is on by default; `SUTRA_MEMORY=off`
turns it off completely.

```
you> I get paid on the 15th, and please keep your answers short
sutra> Got it.
  Noted: You get paid on the 15th.
  Noted: You want short answers.
```

### What is stored, and where

Two SQLite files under `orchestrator/data/` (gitignored, created readable only
by you):

| File | Contents |
|---|---|
| `memory.db` | **Memories**: short durable statements about you (a fact, preference, routine, or correction), each with its source, status, and a link to the conversation it came from. **Recent conversations** (the last 30 days): what you said, the assistant's reply (unless `SUTRA_RECORD_REPLIES=off`), the names and outcomes of the tools called, and whether a confirmation was confirmed or declined. |
| `memory-archive.db` | Conversations older than 30 days, moved here. They are never used as context for the model, never recalled, and never read by anything automatic. Nothing is deleted automatically. |

**Never stored:** raw tool results (so finanxe data is not copied to disk, apart
from figures that appear in a reply you saw), your token, or your API key.

### How memories get made

- **From your own words.** After each reply, a separate small model reads only
  your message (and your previous one) and extracts durable things you stated
  about yourself. It never sees tool results or the assistant's replies, so text
  inside a tool result cannot become a memory. It skips passing moods, questions,
  one-off requests, and credentials.
- **From `/remember <text>`**, directly.
- **From the assistant's suggestions.** The assistant can propose a memory it
  noticed. A proposal does nothing until you run `/approve <id>`; `/reject <id>`
  declines it and it will not be suggested again. Proposals made while the
  assistant was reading tool results are flagged, because that is where
  injected text could come from.

You are told when memory changes: `Noted: ...`, `Updated: ... (replacing: ...)`,
or `I'd like to remember that ...`. A newer statement replaces an older one it
clearly contradicts (the old one stays visible as "replaced").

Only memories you stated, or suggestions you approved, are ever given to the
model as facts about you. A memory can never change what the assistant is
allowed to do: a remembered "no confirmation needed" does not skip a
confirmation.

### Commands

Lines starting with `/` are handled locally and never sent to the model.

| Command | What it does |
|---|---|
| `/memories [query]` | List everything remembered (newest first), or search it. Replaced, proposed, and rejected ones are shown and marked. |
| `/remember <text>` | Add a memory yourself. |
| `/forget <id>` | Delete one memory, including its search-index entry. |
| `/forget all` | Delete every memory. Asks you to type `FORGET`. |
| `/why <id>` | Show the conversation a memory came from, even from the archive. |
| `/proposals`, `/approve <id>`, `/reject <id>` | Review what the assistant wants to remember. |
| `/archive search <text>` | Search old conversations. |
| `/archive purge --before YYYY-MM-DD` | Permanently delete archived conversations. Asks you to type `PURGE`. |
| `/help` | The list. |

### Erasing everything

Memories only: `/forget all`. Everything memory has ever stored, including all
conversations:

```sh
rm -r orchestrator/data
```

Or look at the raw data yourself: `sqlite3 orchestrator/data/memory.db`.

### Measuring it

```sh
.venv/bin/python evals/run_recall_eval.py       # no API key; also runs in the test suite
.venv/bin/python evals/run_extractor_eval.py    # needs ANTHROPIC_API_KEY
```

The recall eval currently gets every ordinary question right and recalls
nothing for unrelated ones, but misses pure paraphrases that share no words
with the memory ("children" for a memory saying "kids", "taxes" for
"accountant"). Keyword search cannot bridge those; if they matter in real use,
an embedding-based retriever can be added behind the `Retriever` seam. The
extractor eval reports precision and recall against a labelled message set and
fails if an injection-style or credential message produces a memory.

### For other code

`MemoryProvider` (`recall` before a turn, `record` after it, optional local
tools) is the interface the orchestrator uses; `NullMemory` does nothing and is
the default when no provider is passed.

## Use it from code

```python
reply = await orchestrator.respond("what do I owe?")   # str in, str out
```

`Orchestrator.respond` has no terminal dependencies; a voice agent calls it
the same way the REPL does. See `src/sutra_orchestrator/__main__.py` for how
it is assembled.

## Tests

```sh
.venv/bin/python -m pytest
```

The unit tests use scripted fakes for the model and the gateway, so they need
no network and no API key. `tests/test_mcp_transport.py` also runs an in-process
MCP server on localhost to exercise the real transport: authentication
failures, truncation, and reconnecting after the gateway restarts.

To measure the confirmation classifier against real model calls (needs
`ANTHROPIC_API_KEY`, costs a few cents):

```sh
.venv/bin/python evals/run_classifier_eval.py
```

It reports accuracy per label, lists every miss, and exits non-zero if any
reply is wrongly classified as a yes. Re-run it whenever the classifier prompt
or model changes.

## Status

Built and covered by tests: connection and auth errors, the turn loop, the
confirmation gate, the memory seam, the REPL, and local memory with
proposals, notices, and the archive. Not yet done, because they need a real API
key and your running gateway: tuning the system prompt against real finanxe and
twin results, a multi-session walkthrough of memory, and measuring real per-turn
latency. Run `--verbose` during that walkthrough; it prints model and tool
timings for each call.
