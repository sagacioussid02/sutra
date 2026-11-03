## Why

The natural companion to an interest profile: when the user is not talking to it, Sutra could spend a small, bounded amount of effort looking into the top current interest — what's on, what changed, what's worth knowing — and have something genuinely useful ready, delivered through the inbox and announced ask-first, instead of the user having to remember to ask. This is the behaviour that makes an always-on assistant feel proactive rather than idle.

**Status: stub — not implemented. This change is gated on the reminders + direct-answers changes (A+B) being dogfooded first, and on Sidd's explicit go-ahead.**

## What Changes (planned)

- A scheduler-driven job (on the reminders change's scheduler) that, when enabled, picks the strongest current interest from the interest profile and runs one bounded research task — through the ephemeral-agents change's sandboxed delegation, never as the main agent — and files the result in the inbox as an unread item.
- Hard limits, enforced in code and off by default: a daily budget (runs and tokens) that stops the job cold when spent, a minimum interval between runs, and a single settings switch that disables idle research entirely. Research runs only while enabled and never spends past the cap "to finish a thought".
- Everything produced is a *finding*, labelled with when it was gathered and from what; findings are data for the main conversation, not memories, until the user engages with one.

## Capabilities

### New Capabilities

- `idle-research`: budgeted background research over the interest profile, delivered as inbox findings. (Stub — no spec yet; the spec is written when this change is picked up.)

## Impact

None yet — stub only. When picked up: depends on `interest-profile` (what to research), `ephemeral-agents` (the sandboxed worker), and `reminders-scheduler` (the scheduler and inbox). Expected to add web access for the research worker, which needs its own review at that time: web content is untrusted input and this job reads it unsupervised.
