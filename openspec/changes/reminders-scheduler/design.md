## Context

Sutra today is request/response: a turn runs, tools fire behind the confirmation gate, memory records what happened. Nothing in the system owns a future obligation. The voice change added background *lanes* for work the user starts and waits on, but a reminder is different — it is created in one breath and must fire minutes or days later, possibly after restarts, with no one watching.

The one hard rule this design is built around: **a reminder is a correctness problem, not a conversation problem.** The model is good at understanding "remind me to call Sam after dinner" and bad at being awake at 5pm. So the model (and the user's words) are involved exactly once — at creation — and everything after that is deterministic code.

## Goals / Non-Goals

**Goals:**

- "Remind me ..." (spoken or typed) and `/remind` create a reminder whose fire time is fixed, stored, and confirmed back to the user word-for-word.
- A reminder fires exactly once, on time while the process runs, and once — marked late — after a restart if it came due while the process was down.
- The firing path contains no model call, no classifier call, and no network dependency.
- Times survive timezone and DST edges by construction, not by testing luck.
- The inbox is the one place fired reminders land, minimal enough to build inside this change.

**Non-Goals:**

- Recurring reminders ("every Tuesday"), snoozing, and editing a reminder's time. Cancel and re-create covers the MVP.
- A generic notification platform: priorities, channels, retries, templates. The inbox is a table and a list command.
- Spoken announcement of a fired reminder in the voice client. Fired reminders land in the inbox there; speaking them must go through the ask-first notification pattern from the voice work and is future work.
- Natural-language time understanding beyond the listed forms. "After dinner" is a clarification request, not a parse.
- Cross-device delivery or OS notifications.

## Decisions

### Parse once, deterministically, at creation

`reminders/parser.py` is a set of anchored regular expressions over a closed grammar: relative offsets (`in N minutes/hours`, `in an hour`, `in half an hour`), and wall-clock times (`at 5pm`, `at 5:30pm`, `at 17:30`, `at noon`, `at midnight`) optionally prefixed by `today` or `tomorrow`. The output is a `ParsedReminder(fire_at, text)` or `None`.

Rules that keep it honest:

- A bare hour with no am/pm and no colon (`at 5`) returns `None` — am vs pm would be a guess.
- Bare `at <time>` means today, rolling to tomorrow only if that time has already passed. `today at <time>` never rolls: a past time returns `None` so the user hears about it instead of silently getting tomorrow.
- A time with no reminder text returns `None`; there is nothing to remind about.
- The parser never calls the model. If a future change wants model-assisted parsing, the model may propose a structured time but this parser's output (or an equivalent validated structure) is still what gets stored — the store never holds raw words.

### Two kinds of time, handled differently

A fire time is stored as an absolute instant (UTC ISO string), so comparisons are trivial and restarts are safe. But the two input kinds compute that instant differently:

- **Relative** ("in 24 hours") is elapsed time: computed in UTC and converted to the user's zone for display. Across the spring-forward it lands at 13:00 local, not 12:00 — that is what "in 24 hours" means.
- **Wall-clock** ("tomorrow at 9am") is local time in the configured zone: built with `zoneinfo` arithmetic so 9am after the spring-forward is 9am MDT (UTC−6), not a UTC-shifted 10am or 8am.

### The store mirrors the memory store

`reminders.db` sits next to `memory.db` (same directory by default), is created owner-only (`0600`), carries a `PRAGMA user_version` schema version that refuses a newer file rather than modifying it, and is plain SQLite the user can inspect. Two tables: `reminders` (the jobs) and `inbox` (deliveries). Keeping them in one file means one backup and one privacy story.

### Firing is a claim

The scheduler polls the store on a short interval (5s). For each due reminder it runs one guarded update:

```sql
UPDATE reminders SET status='fired', fired_at=?, late=?
WHERE id=? AND status='pending'
```

Only the caller whose update changed the row delivers the reminder (inserts the inbox row, runs the delivery callback). This is the gateway Claims pattern — single-use, atomic, first-writer-wins — applied to time instead of confirmations. A REPL process and a voice process sharing the file, or a duplicated scheduler loop, cannot double-deliver. Cancellation uses the same guarded shape (`pending -> cancelled`), so a cancel racing a fire has exactly one winner.

### Missed-fire policy: fire once, marked late

The scheduler records when it started. On each sweep, a due reminder whose fire time is **before the scheduler started** is one that came due while the process was down: it is claimed, delivered, and marked `late` in the inbox (and the REPL prints it with a "came due while I was off" note). A reminder that comes due while the scheduler runs is on time. The alternative — silently dropping missed reminders — was rejected: a reminder that vanishes because a laptop slept is the worst failure this feature can have, worse than a late one. Firing *without* the late mark was rejected too: the user should know the 5pm reminder arrived at 9am.

### The inbox is deliberately minimal

An inbox row is a delivery record: which reminder, its text, when it was due, when it was delivered, whether it was late, and whether it has been seen. `/inbox` lists it. That is all. It exists because two already-planned consumers need exactly this shape — the voice client's ask-first announcements and later background results — and building it inside this change keeps those changes from inventing their own. Anything more (priorities, channels, digests) waits for a consumer that needs it.

### Where the surfaces plug in

- `Orchestrator.respond()`: after the addressee gate and the pending-confirmation branch, before the model turn, an utterance starting with "remind me" (case-insensitive) goes to `ReminderService.try_handle`. Precedence matters: a pending confirmation still wins, so "yes" can never be eaten by the reminder path, and a reminder request can never confirm an action. The service appends the exchange to history itself (the model's later turns can see the reminder was set) and never touches pending state. With no service configured, the hook is inert.
- REPL: `CommandSet` tries handlers in order and the first non-`None` result wins; reminder commands are tried first because the memory handler answers *every* `/` line (with "unknown command") and would otherwise swallow them. `/help` gains the reminder commands.
- Voice: the entry point wires the same store, service, and scheduler. The `respond()` hook works spoken as-is; fired reminders go to the inbox (see Non-Goals for spoken announcement).

## Risks / Trade-offs

- **The parser will refuse phrases users expect to work** ("remind me after dinner", "remind me next Friday"). Mitigation: the refusal is a specific clarification with examples of forms that work, and every refusal is visible in the conversation — the failure mode is an annoyed rephrase, never a silently wrong time.
- **Poll latency up to one interval (5s).** Acceptable for human reminders; the interval is a constructor parameter if a future consumer needs tighter firing.
- **Two processes, one file.** SQLite locking plus the atomic claim make double-delivery impossible; a locked-database error would surface as a failed sweep and retry next interval, delaying but not losing a reminder.
- **The `respond()` hook bypasses the model entirely**, including the memory extractor's view of raw turns — but the exchange is written to history and recorded as an episode like any fixed reply, so recall still sees it.
