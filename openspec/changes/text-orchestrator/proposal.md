## Why

Phase 1 ends with a gateway that works, but the only way to use it is
`sutra-cli`: type an exact tool name, type JSON arguments, read JSON back.
Nothing yet turns "how much debt do I have?" into a tool call, or turns the
JSON result into a sentence. That translation layer — an LLM connected to
the gateway as an MCP client — is the brain Phase 2's voice pipeline needs,
and it is much cheaper to build and debug in text than over audio. Building
it now, as a standalone text agent, means the voice work later is only
STT and TTS wrapped around something already proven.

## What Changes

- Add a new Python package, `orchestrator/`, alongside `gateway/`. It is a
  separate process and a pure client of the gateway's existing MCP
  interface.
- The orchestrator connects to the gateway with a user's bearer token,
  fetches the tools that user may call, and offers them to a Claude model
  as callable tools.
- A turn function takes one user utterance as text and returns one reply as
  text: the model picks tools, the orchestrator calls them through the
  gateway, the model reads the JSON results and writes a short, speakable
  answer.
- Confirm-first calls are handled as a two-turn exchange: the reply reads
  back the gateway's pending description and asks for confirmation; only an
  affirmative on the user's next turn calls `gateway_confirm`. The
  decision to confirm is made by orchestrator code, not by the
  conversational model.
- The user's reply to a confirmation is classified by intent, so "yes" and
  "sure, sounds good" are treated the same. An isolated classifier sees
  only the pending description and the user's reply.
- A terminal REPL (`python -m sutra_orchestrator`) for typing to the agent.
- A system prompt that enforces voice-ready output: brief, no tables or
  markdown, rounded numbers, no raw ids or JSON.
- A memory interface (`recall` before a turn, `record` after) with a
  do-nothing default. This is the seam where the assistant's long-term
  memory, and later its learning, plug in; the real store is the separate
  `assistant-memory` change. Sutra's end goal is an assistant that knows
  the user and improves with use, and this change is built so that is not
  a rewrite.
- No audio in this change. No STT, TTS, LiveKit, or hardware.

## Capabilities

### New Capabilities
- `text-orchestrator`: a text-in, text-out conversational agent that
  answers natural-language requests by calling Sutra gateway tools, replies
  in speakable language, and gates confirm-first actions behind an explicit
  user confirmation

### Modified Capabilities
(none)

## Impact

- New code only, under `orchestrator/`. First Python in this repo; the
  gateway stays Go.
- No changes to the gateway, twin, or finanxe. If the orchestrator needs
  something the gateway does not provide, that is a gap to raise as its own
  change, not to patch around here.
- New dependencies: the Anthropic Python SDK and the MCP Python SDK.
- New runtime requirement: an `ANTHROPIC_API_KEY`. Tool results, including
  finanxe financial data, are sent to the Anthropic API as model context.
  finanxe's own agent already does this, but it is new for the gateway
  path and for twin data.
- Depends on Phase 1 being complete (`gateway-core`, the twin and finanxe
  tool changes, `agent-discovery`). `sutra-cli` is kept as the low-level
  debugging client.
