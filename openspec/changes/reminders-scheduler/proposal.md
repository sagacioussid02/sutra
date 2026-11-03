## Why

Sutra can remember things and act on request, but it cannot act later. "Remind me at 5pm to take the bins out" has nowhere to go: there is no scheduler, no durable job store, and no delivery surface, so a reminder either becomes a memory (never fired) or a model promise (never kept). Reminders are the first time-based behaviour and the proving ground for every later scheduled behaviour — interest reflection, idle research, and background work all need the same durable scheduler and the same place for finished work to land.

## What Changes

- A deterministic reminder parser (no model) that turns a small set of spoken forms — "in N minutes/hours", "at 5pm" / "at 17:30" (today, or tomorrow if already past), "today at ...", "tomorrow at ..." — into one structured job at creation time. Anything it cannot pin down returns no job; the user is asked to rephrase. It never guesses a time.
- A durable SQLite reminder store (private file, schema-versioned, following the memory store's pattern) holding the job once: text, fire time, timezone, status.
- A deterministic asyncio scheduler with **no model in the firing loop**. Firing is an atomic status claim (`pending -> fired` in one guarded update, the same shape as the gateway's confirmation Claims), so a reminder is delivered exactly once even if two loops race.
- A missed-fire policy, stated plainly: **if the process was down when a reminder came due, the reminder is not dropped. On the next start it fires exactly once and is marked late**, so the user can tell it arrived after the fact.
- A minimal inbox for fired reminders — a store table plus a list surface — built inside this change, not as a generic notification platform. Later changes (idle research, background results) may reuse it.
- Timezone-aware throughout: wall-clock times are read in a configurable timezone (`SUTRA_REMINDERS_TZ`, default America/Denver) using `zoneinfo`; relative times are elapsed time, so "in 24 hours" stays 24 hours across a DST change.
- User surface in the existing styles: a `respond()` hook ("remind me ..." is parsed deterministically before any model call; success confirms the exact fire time; failure asks for clarification) and REPL commands in the `/memories` pattern: `/remind <when> <what>`, `/reminders`, `/reminders cancel <id>`, `/inbox`.

## Capabilities

### New Capabilities

- `reminders-scheduler`: deterministic parsing of reminder requests into structured jobs, durable storage, exactly-once firing with the missed-fire (late) policy, timezone and DST correctness, and the reminder/inbox user surface.

### Modified Capabilities

<!-- None: memory, episodes, and the confirmation flow are untouched. -->

## Impact

- New Python package `orchestrator/src/sutra_orchestrator/reminders/` (db, parser, store, scheduler, service, commands). Python orchestrator only; the Go gateway is unchanged.
- `Orchestrator` gains an optional `reminders` dependency and a pre-model hook in `respond()`; with no service configured, behaviour is exactly as before.
- `Config` gains `SUTRA_REMINDERS` (on/off), `SUTRA_REMINDERS_DIR`, and `SUTRA_REMINDERS_TZ`.
- The REPL gains a small command-chain dispatcher so reminder commands can be tried before the memory commands (which answer every `/` line); `/help` lists the new commands. The voice entry point wires the same service and scheduler; fired reminders land in the inbox there too.
- New tests in `orchestrator/tests/test_reminders.py` cover the parser, persistence across reopen, exactly-once and double-claim prevention, the late path, a DST case spanning the US spring-forward, the `respond()` hook, and the commands.
