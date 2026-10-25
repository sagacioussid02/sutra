## Context

This is deliberately the last Phase 1 change and deliberately thin: it's a
client of the MCP interface the gateway already exposes, not a place for
new gateway logic. It exists so there's a way to actually use and
demonstrate everything built so far, and so the confirm-first UX is
validated on a keyboard before it has to work over voice.

## Goals / Non-Goals

**Goals:**
- One command to run that connects to the gateway with a given user's
  token and drops into an interactive session.
- Confirm-first calls are visibly distinct from read-only ones — the user
  sees the pending description and must type something explicit (e.g.
  `yes`/`no`) rather than the flow silently proceeding.
- A repeatable walkthrough script/doc that exercises: twin chat, finanxe
  snapshot, a finanxe mutation held for confirmation and then confirmed.

**Non-Goals:**
- Any audio/voice input — text only.
- A polished UI — a REPL-style terminal loop is sufficient.
- New gateway-side behavior — if the CLI needs something the gateway
  doesn't do yet, that's a gap in an earlier change, not something to patch
  around here.

## Decisions

- **Transport**: standard MCP client library talking to the gateway over
  whatever transport `gateway-core` settled on (stdio or local HTTP) — no
  custom protocol.
- **Interaction loop**: list available tools for the authenticated user ->
  prompt for a tool name and arguments (simple structured prompts, not a
  full argument parser) -> dispatch -> if a pending confirmation comes
  back, print the description and require an explicit `yes` to call
  `confirm()`, anything else cancels (no execution, no implicit timeout
  handling beyond what `gateway-core` already does server-side).
- **Walkthrough**: documented as a short script in the client's own
  README/usage text, run manually rather than fully automated, since it
  depends on both twin and finanxe being reachable.

## Risks / Trade-offs

- A REPL-style CLI won't fully predict how a voice interaction will feel
  (turn-taking, interruption) — that's expected; its job is to validate the
  gateway's contract, not to be a voice UX prototype.
