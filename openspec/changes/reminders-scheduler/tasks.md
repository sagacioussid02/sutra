## 1. Store

- [x] 1.1 Add `reminders/db.py`: schema (reminders + inbox tables), `PRAGMA user_version` check that refuses a newer file unmodified, owner-only (0600) database file, mirroring the memory store
- [x] 1.2 Add `reminders/store.py`: add / get / list_pending / cancel / due, the atomic `claim` (single guarded `pending -> fired` update; only the winner may deliver), and inbox deliver / list / mark_seen

## 2. Deterministic parser

- [x] 2.1 Add `reminders/parser.py`: "remind me" request extraction plus the closed grammar — "in N minutes/hours", "in an hour", "in half an hour", "at <time>" (5pm, 5:30pm, 17:30, noon, midnight), "today at ...", "tomorrow at ..."
- [x] 2.2 Refuse, never guess: bare hour without am/pm, "today at" a past time, unknown phrasing, and a time with no reminder text all return None
- [x] 2.3 Time arithmetic: relative offsets computed as elapsed time in UTC; wall-clock times built in the configured zoneinfo timezone so DST transition days resolve to the correct offset

## 3. Scheduler

- [x] 3.1 Add `reminders/scheduler.py`: asyncio poll loop; each sweep claims due reminders atomically and delivers each exactly once to the inbox, with an optional delivery callback
- [x] 3.2 Missed-fire policy: the scheduler records its start time; reminders that came due before it are fired once on the first sweep and marked late; on-time deliveries are not marked late

## 4. User surface

- [x] 4.1 Add `reminders/service.py`: `try_handle` for "remind me ..." utterances — success stores the reminder and confirms the exact fire time in spoken form; failure returns a clarification reply with examples
- [x] 4.2 Hook the service into `Orchestrator.respond()` after the addressee gate and the pending-confirmation branch, before any model call; record the exchange in history without touching pending state; inert when no service is configured
- [x] 4.3 Add `reminders/commands.py` in the `/memories` command style: `/remind <when> <what>`, `/reminders`, `/reminders cancel <id>`, `/inbox`; unknown commands return None so handlers can chain
- [x] 4.4 Add a `CommandSet` dispatcher to the REPL (first non-None handler wins), wire reminder commands before memory commands in `__main__`, and list the new commands in `/help`

## 5. Configuration and wiring

- [x] 5.1 Add `SUTRA_REMINDERS` (on/off), `SUTRA_REMINDERS_DIR` (defaults to the memory directory), and `SUTRA_REMINDERS_TZ` (default America/Denver, validated as a real zone) to config and `.env.example`
- [x] 5.2 Wire store, service, and scheduler into the text REPL entry point: scheduler runs as a background task, fired reminders print a line and land in the inbox
- [x] 5.3 Wire the same store, service, and scheduler into the voice entry point (the "remind me" hook works spoken; fired reminders land in the inbox)
- [ ] 5.4 Spoken announcement of a fired reminder in the voice client, through the ask-first notification path (future work; the inbox is the delivery surface for this change)

## 6. Tests

- [x] 6.1 Parser tests: relative, clock time (today and rollover), "today at", "tomorrow at", 24-hour form, noon, and the refusal cases (bare hour, unknown phrasing, past "today at", no text)
- [x] 6.2 DST tests spanning the US spring-forward: wall-clock "tomorrow at 9am" resolves to MDT; "in 24 hours" is 24 elapsed hours
- [x] 6.3 Store tests: add/list/cancel, persistence across reopen (restart survival), owner-only file permissions
- [x] 6.4 Scheduler tests: fires exactly once across repeated sweeps, double-claim prevention across two store connections, missed-fire delivered once and marked late, on-time delivery not late, run-loop delivery
- [x] 6.5 Surface tests: `respond()` "remind me" hook (no model call, exact confirmation, clarification on failure, ordinary turns unaffected, inert without a service), REPL commands end to end, inbox listing with the late mark
- [x] 6.6 Config tests: reminder defaults, `SUTRA_REMINDERS=off`, timezone override, invalid timezone rejected

## 7. Documentation

- [x] 7.1 README: a Reminders section covering the spoken forms, the exact-fire-time confirmation, restart and late behaviour, the inbox, the commands, and the configuration switches
