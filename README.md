# Sutra

Sutra is a personal, voice-activated gateway that sits in front of the user's
existing AI agent projects (trading, financial analysis, persona AI,
journaling, ...) and lets them be reached through one unified, conversational
interface. Long-term it grows into: unified orchestration -> voice ->
dedicated hardware, with auth, audit, and observability built in from the
start rather than retrofitted.

See [`prd.txt`](./prd.txt) for the original hardware/voice vision. This
README documents the architecture actually being built, phase by phase, and
`openspec/changes/` holds the implementation plan.

## Phased roadmap

1. **Unify** — MCP gateway in front of existing agent projects. *(current phase)*
2. **Voice** — LiveKit Agent + LLM on a laptop mic, talking to the gateway.
   Built in steps, text first:
   1. **Text orchestrator** ([`orchestrator/`](./orchestrator)) — an LLM agent
      that turns typed requests into gateway tool calls and the JSON results
      back into short spoken-style replies, with a safe spoken-style
      confirmation flow. This is the brain the voice layer wraps.
   2. **Assistant memory** ([`orchestrator/`](./orchestrator#memory)) — a local,
      inspectable store so it knows you across sessions: it remembers what you
      tell it, tells you when it does, lets you approve what it wants to
      remember, and lets you see, correct, and erase all of it.
   3. **Voice** — STT and TTS around the same `respond()` call.
3. **Platform** — RBAC for trusted users, per-user tool config, full observability.
4. **Hardware** — Raspberry Pi 5 + ReSpeaker client joining the same voice session.

## Phase 1 architecture: the MCP gateway

Phase 1 wraps existing projects behind one MCP server. It does not rewrite
those projects — it calls into what they already expose (an HTTP endpoint, a
Python function) and presents a curated, permissioned tool list to whatever
orchestrator (today: a CLI client; later: the voice orchestrator) talks to it.

```
                         +---------------------------+
                         |   Client (Phase 1: CLI)    |
                         |   (Phase 2+: voice/LiveKit) |
                         +--------------+--------------+
                                        | bearer token (per trusted user)
                                        v
                         +---------------------------+
                         |        Sutra Gateway        |
                         |  (single local process)     |
                         |                             |
                         |  - Auth: per-user token ->   |
                         |    allowed tools mapping     |
                         |  - Tool registry (tiered):   |
                         |      read-only               |
                         |      confirm-first            |
                         |      never-by-voice           |
                         |  - Confirmation flow for      |
                         |    confirm-first tools        |
                         |  - Audit log (every call:      |
                         |    who/tool/args-redacted/     |
                         |    result/timestamp)           |
                         +----+-------------------+-------+
                              |                    |
                 in-process / localhost call       |
                              v                    v
                 +------------------+   +----------------------+
                 |  twin adapter    |   |  finanxe adapter      |
                 |  (read-only)     |   |  (mixed tiers)        |
                 +--------+---------+   +-----------+----------+
                          |                          |
                          v                          v
              +------------------------+   +--------------------------+
              | twin backend            |   | finanxe backend           |
              | FastAPI, Clerk JWT      |   | stdlib http.server        |
              | already deployed on AWS |   | localhost:8002 only        |
              | (Lambda/S3/CloudFront/  |   | Plaid tokens (encrypted    |
              | Bedrock)                |   | via .finanxe_key), SQLite, |
              |                         |   | Anthropic tool-calling      |
              |                         |   | agent (analyzer/optimizer  |
              |                         |   | give real numbers)          |
              +------------------------+   +--------------------------+
```

### Design decisions

- **Gateway is local-only in Phase 1.** No cloud exposure yet, matching the
  "prefer cheap/simple hosting" and "sensitive data" constraints. finanxe
  stays bound to `127.0.0.1`; the gateway is the only caller.
- **Secrets never cross the adapter boundary.** Plaid access tokens and the
  finanxe encryption key stay inside finanxe's process. The gateway only ever
  sees tool inputs/outputs, never raw credentials.
- **Tool tiers, decided at registration time, not at call time:**
  - `read-only` — safe to call directly (snapshots, chat, lookups).
  - `confirm-first` — gateway holds the call, requires an explicit
    confirmation step before executing (e.g. `set_debt_funding_by_name`).
  - `never-by-voice` — not exposed as a callable tool at all in Phase 1
    (e.g. anything touching raw Plaid tokens).
- **Audit log from day one.** Every tool invocation is recorded (caller,
  tool, redacted args, result, timestamp) before Phase 3's broader
  observability work — this is foundational, not an add-on, because finanxe
  holds real financial data.
- **Auth is per-trusted-user bearer tokens**, not a full multi-tenant system —
  matches "me + a few trusted users," not a public product.

## Implementation plan

The above is broken into five OpenSpec changes under `openspec/changes/`:

1. `gateway-core` — gateway process skeleton: auth, tool registry with tiers,
   confirmation flow, audit log. No project-specific tools yet.
2. `mcp-tools-twin` — wraps twin's `/chat` and read endpoints as read-only
   MCP tools.
3. `mcp-tools-finanxe-readonly` — wraps finanxe's snapshot/debt/calendar
   reads as read-only MCP tools.
4. `mcp-tools-finanxe-confirm` — wraps finanxe's mutating functions
   (`set_debt_funding_by_name`, `create_tracked_goal`, ...) as confirm-first
   tools, using the confirmation flow from `gateway-core`.
5. `gateway-cli-client` — a text CLI that exercises the whole gateway
   end-to-end: ask twin a question, ask finanxe for a snapshot, attempt a
   mutating action and get stopped for confirmation. This is the Phase 1
   milestone — no voice yet.

Run `openspec list` in this repo to see current change status.
