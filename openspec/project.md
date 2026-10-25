# Sutra

## What this is

A personal MCP gateway that unifies the user's existing AI agent projects
behind one auth/tool/audit layer, eventually fronted by voice and dedicated
hardware. See `../README.md` for the full architecture and phased roadmap.

## Current phase

Phase 1: MCP gateway wrapping two existing projects, no voice yet.

- **twin** (`~/workspace/AI/twin`) — deployed persona-chat platform. FastAPI
  backend, Clerk JWT auth, AWS Lambda/S3/CloudFront/Bedrock. Low risk,
  read-only tools only.
- **finanxe** (`~/workspace/AI/finanxe/poc`) — local POC financial copilot.
  Plaid bank connections (encrypted tokens via `.finanxe_key`), SQLite,
  Anthropic tool-calling agent (`agent.py`) backed by a deterministic engine
  (`analyzer.py`/`optimizer.py`) so numbers are never hallucinated. Runs on
  `127.0.0.1:8002` via stdlib `http.server`. **Sensitive**: real bank data,
  no access control today. Some functions are side-effecting
  (`set_debt_funding_by_name`, `create_tracked_goal`,
  `agent_add_calendar_event`).

## Constraints

- Audience: the user plus a few trusted people — not a public product (yet).
  Simple per-user bearer tokens, not full multi-tenancy.
- Hosting: prefer cheap/simple (local process, VPS later) over AWS-heavy
  infra. Not attached to Bedrock — direct Anthropic API is fine.
- finanxe holds real financial data: secrets (Plaid tokens, `.finanxe_key`)
  must never leave finanxe's own process; the gateway only sees tool
  inputs/outputs.
- Every tool call must be tiered at registration: `read-only`,
  `confirm-first`, or `never-by-voice` (not exposed). Side-effecting finanxe
  tools are `confirm-first` at minimum.
- Audit logging (caller, tool, redacted args, result, timestamp) is
  foundational — built in `gateway-core`, not deferred to a later phase.

## Conventions

- Existing projects (twin, finanxe) are not modified to fit the gateway;
  adapters call their existing HTTP endpoints / functions as-is.
- Each OpenSpec change should be small enough to scaffold and review on its
  own; see `../README.md` for the current change breakdown.
