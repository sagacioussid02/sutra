## Context

Sutra today: a merged MVP plus the A–F roadmap (reminders, direct
answers, ephemeral agents, interest profile, episode graph with offers,
idle research, self-learning), speaker-bound confirmations, and the
PR #7-era changes (inbound events, world-state, speaker-addressee,
memory distillation). The suite is ~960 tests, all against fakes. The
post-MVP review's central finding stands: nothing has run live, the
dogfood gate was skipped, and every remaining unknown is behavioural —
does it do the right thing across a long, messy conversation?

Two constraints shape this design. First, the user's time is the
scarcest resource in the project; a harness that needs the user present
is a harness that doesn't run. Second, whatever the harness produces
must be trustworthy enough to ground a hardware purchase decision and
clean enough to train on — so grading and labelling discipline are the
design, not an afterthought.

## Goals / Non-Goals

**Goals:**
- Sustained, repeatable, headless exercise of the real respond pipeline
  across the behaviours the hardware decision depends on.
- Grading that is deterministic wherever the outcome is checkable, with
  rubric judgement quarantined to soft criteria.
- A versioned, labelled, committable dataset of turns (speech act,
  addressee, outcome) that `speech-act-addressee-classifier` can train
  on.
- A readiness scorecard with a trend, per capability.
- Failures that can never be silently lost: every one becomes an eval
  case or a lesson proposal.

**Non-Goals:**
- Fixing what the batteries find. Fixes land as ordinary changes/PRs by
  the usual route; the harness only reports and preserves.
- Replacing the user's real usage. Simulation cannot prove the living
  room: microphone pickup, real speaker identification, real event
  sources. The scorecard says what simulation proved, labelled as such.
- Training anything. This change produces data and scores; training is
  `speech-act-addressee-classifier`.
- Live side effects of any kind — no speech, sends, bookings, payments,
  or writes to real stores, ever, from a battery.

## Decisions

### The harness drives the production respond pipeline, in a sandbox profile
Batteries are conversations sent through `Orchestrator.respond` via the
text/repl seam, against a sandbox profile: fresh throwaway stores
(memory, episodes, lessons, offers), synthetic users, a fake clock the
battery controls, and mutating tool adapters replaced by recording
stubs at the adapter boundary. Everything between the seam and the
adapters — parsing, classification, the confirmation flow, the arbiter,
the scheduler logic — is the production code.

*Why:* a harness with its own pipeline proves nothing about the real
one; a harness with real adapters is dangerous. The adapter boundary is
the one seam where simulation can be total without being fake. The fake
clock is what makes firing behaviour testable at all: a battery can
create a reminder, advance time across a DST boundary, restart the
scheduler, and assert exactly-once firing, in seconds.

### Batteries are targeted scenarios with expectations written in advance
Each scenario declares its turns, its labels, and its expected outcomes
*before* it runs: the reminder fires at instant X; the sarcastic reply
executes nothing; turn 40 still honours the constraint set at turn 3.
Generated scenarios are instantiations of templates with the same
property — the generator knows the intent of every turn it writes,
which is what makes the labels ground truth rather than a grader's
opinion.

*Why:* expectations-first is what separates an eval from two AIs
chatting. Open-ended autopilot conversation produces anecdotes; a
scenario with a pre-registered outcome produces evidence, and its turns
are labelled for free because the generator authored the intent.

### Grading is two-tier and the tiers never mix
Deterministic checks run in code and produce pass/fail. Rubric grading
(a model applying a written rubric to a transcript) produces a separate
soft score with the rubric text and the grader's rationale stored. The
scorecard reports the tiers in separate columns. A rubric pass can
never override a deterministic failure.

*Why:* the grader model is a noisy judge, gameable and drifting. For
safety-relevant behaviour (confirmations, firing, caps) the check must
be as trustworthy as the behaviour it guards. Rubric judgement is still
valuable — tone and offer timing have no deterministic oracle — so it
is kept, labelled, and fenced.

### Every failure is promoted to the eval corpus verbatim
A failing scenario is copied — turns, labels, expectations, observed
behaviour — into the permanent eval corpus with a stable id. Subsequent
runs include the corpus; a fix is only evidenced when the case passes,
and the case is never deleted for passing.

*Why:* this is the harness's memory, and the project's regression
insurance. It mirrors the confirmation classifier's eval discipline
(129 cases, zero false affirms) extended to whole conversations.

### The dataset is versioned and the scorecard is append-only
The labelled dataset is JSONL in-repo with a manifest (dataset version,
battery set version, per-label counts, checksum). A run that adds turns
bumps the dataset version; training in the follow-on change pins a
version. The scorecard is an append-only file of per-run,
per-capability results in both grading tiers.

*Why:* training against a moving dataset makes results irreproducible,
and a hardware decision needs a trend line, not a snapshot. Append-only
keeps both honest: nothing is rewritten after the fact.

### Lessons flow through the existing gate, untouched
Repeated failure shapes (same expectation, same failure mode, N runs)
are summarised into draft lesson proposals in the `self-learning`
format, entering that system as `proposed`. Approval remains the
user's, the probe gate still applies, and the harness holds no approval
tool. If a failure is a bug rather than a behaviour preference, the run
report says so and names the failing scenario id; the fix is a normal
PR, never a lesson.

*Why:* the self-learning design's core rule — Sutra proposes, only the
user disposes, and nothing learned touches the confirmation gate — is
the safety story of the whole learning roadmap. The harness feeds that
loop; it does not route around it.

### The confirmation gate is a test subject, never a student
The invariant for the whole roadmap, stated here because this change
builds the feedback machinery: **the confirmation gate before
irreversible actions stays rule-based permanently, held to its
zero-false-affirm eval bar.** Batteries attack it (sarcasm, ambiguity,
bystanders, expired claims) precisely because it must not learn its way
softer. Learned models elsewhere in the roadmap may advise it as a soft
second signal; they may never replace it or lower its bar.

## Risks / Trade-offs

- [Batteries teach to the test] → generated scenarios vary surface form
  from templates each run, the eval corpus is append-only, and the
  scorecard distinguishes battery scores from held-out corpus scores.
- [Grader-model drift makes trends incomparable] → deterministic tier
  is the trend of record; rubric tier records grader model and rubric
  version per run, and a rubric change restarts that column.
- [Synthetic conversations miss real-world mess] → accepted and stated
  on the scorecard: simulation narrows the unknown, the user's live use
  closes it. Batteries are seeded from real failure shapes the review
  and classifier evals already found, not invented in a vacuum.
- [The harness itself has side effects] → sandbox profile only, mutating
  adapters stubbed at the boundary, no network targets except the model
  API the orchestrator already uses, and a run aborts if the profile is
  not the sandbox profile.
- [Dataset quietly accumulates personal data] → batteries are synthetic
  by construction and read no real stores; a dataset lint rejects turns
  containing configured personal markers before commit.

## Migration Plan

Additive and off by default: a CLI entry point and a package, nothing
in the live path changes. First runs are manual and small (one battery)
to validate grading against hand-checked transcripts. Scheduling
(alongside the existing 72-hour build cadence) comes only after the
manual runs are trusted. Dataset and scorecard start empty and are
created by the first run.

## Open Questions

- Run cadence and budget: batteries cost model calls. Start with a
  weekly full run plus on-demand single batteries, and set a per-run
  call budget in config — tune after the first runs show real costs.
- Which grader model for the rubric tier: the same model as the
  orchestrator (consistent, but grading its own family) or a different
  one (more independent, more cost)? The rubric tier is advisory, so
  start with the same model and record it; revisit if soft scores look
  inflated against hand checks.

## Implementation notes

Decisions made while building, recorded so the spec and the code agree:

- **Scripted and live modes.** The runner takes any model. The default
  scripted model is free and deterministic (fixed reply, never calls a
  tool, labels every unsettled confirmation reply `unclear`), which is
  enough for the reminder, confirmation-gate and offer batteries and lets
  the whole harness run in the unit tests. Scenarios that only mean
  something against the real model are marked `requires_live` and are
  skipped, and counted as skipped, in scripted runs.
- **Lesson drafts are written to a file, not to the lesson store.** Writing
  into the self-learning store during a run would contradict "no writes to
  real stores". Drafts go to `lesson_proposals.jsonl`; the user runs
  `dogfood import-lessons <lessons dir>`, which adds them as `proposed`.
  The lesson store's schema allows only `correction` and `outcomes` as a
  source, so imported drafts use `outcomes`; the dogfood provenance (key,
  reason, run) stays in the proposals file. No change to `self-learning`.
- **The dataset adds each turn once.** A turn already present (same
  scenario fingerprint, position and text) is not appended again, so fixed
  batteries contribute on their first run and generated batteries add only
  new wordings; the version bumps only when turns are added. This keeps
  repeated or scheduled runs from churning the committed dataset with
  duplicates.
- **Generated scenarios carry their template.** The classifier change
  should split train/dev/test by template, not by scenario: two scenarios
  from one template share phrasing, so a by-scenario split would still
  leak.
- **Seeding a pending confirmation.** Confirmation traps start from a
  pending action set directly on the orchestrator (the same state a real
  confirm-first tool call leaves), so a trap never depends on the model
  choosing to call the tool. `conf-live-request-then-hedge` covers the
  path where the model makes the request itself.
