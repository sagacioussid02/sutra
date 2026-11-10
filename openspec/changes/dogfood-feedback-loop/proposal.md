## Why

Sutra's capabilities have been built and unit-tested, but almost nothing
has run end to end in sustained conversation: the tests drive fakes, and
the dogfood gate the roadmap set (use A+B for real, then judge) keeps
competing with everything else for the user's time. The hardware
decision — is Sutra ready for an expensive always-on node? — currently
has no evidence base beyond "the test suite is green".

This change builds that evidence base without costing the user hours:
a headless dogfood harness that holds targeted conversations with
Sutra itself, grades them, and keeps score. It is step 1 of the
gradient-learning roadmap for a second reason: every turn it runs is
labelled and versioned, and that labelled dataset is the training fuel
for `speech-act-addressee-classifier`. Targeted, graded, synthetic
episodes give Sutra high-quality failures in days instead of the
household producing them over months.

## What Changes

- **A headless harness in the orchestrator.** A runner drives
  conversations through the same `Orchestrator.respond` pipeline the
  text/repl seam (`text-chat-surface`) uses — no separate test brain, no
  back doors. Sutra under test is Sutra as deployed, minus live side
  effects (below).
- **Targeted scenario batteries.** Scripted scenarios plus scenarios
  generated fresh each run from templates, covering: reminder parsing
  and firing (timezones, DST edges, missed-fire recovery on restart);
  confirmation traps (sarcasm, "yeah no", hedged non-affirmations, a
  bystander answering a claim bound to someone else); direct answers
  (volatile facts must be checked, personal/financial facts stay
  tool-only); cross-session memory recall (state something in session
  one, ask in session three); offer discipline (caps respected, nothing
  offered while a confirmation is pending, no repeat of a dismissed
  offer); and long-conversation drift (a ~40-turn conversation whose
  early facts and constraints are probed at the end).
- **Grading, deterministic first.** Wherever an outcome is checkable in
  code it is checked in code: did the reminder fire exactly once at the
  right instant, did a non-affirmation execute nothing, did the offer
  count exceed the cap. Rubric judgement (a grader model applying a
  written rubric) is used only for soft criteria — tone, offer timing,
  answer quality — and rubric verdicts are stored alongside, never
  merged into, the deterministic pass/fail.
- **Every turn labelled.** Each user turn in every battery is stored
  with its intended `speech_act` (request / chat / rhetorical / joke /
  aside) and `addressee` (sutra / other-person / unclear), plus the
  graded outcome. Stored as a versioned dataset in-repo (JSONL with a
  dataset manifest: version, battery versions, counts per label), so
  `speech-act-addressee-classifier` trains against a pinned dataset
  version, never a moving target.
- **Failures become permanent eval cases.** Any scenario that fails is
  promoted, verbatim, into the eval corpus. It stays there after it is
  fixed: Sutra can never silently regress on a mistake it has already
  made once.
- **Lessons stay proposals.** Recurring failures of the same shape are
  summarised as draft lesson proposals in the existing `self-learning`
  format, approval-gated by the user exactly as today. The harness has
  no tool that approves a lesson, and no path from a battery result to
  a code, prompt, permission, or confirmation-gate change.
- **A readiness scorecard.** Each run appends per-capability scores
  (reminders, confirmations, answers, memory, offers, drift) to a
  scorecard file in-repo, so the hardware-readiness question can be
  answered from a trend — "confirmations: 100% across the last N runs;
  drift: improving, two known failure shapes" — instead of a vibe.
- **Simulation only, no live side effects.** Batteries run against a
  sandbox profile: tools are the real implementations pointed at
  throwaway local stores and a fake clock where firing matters, and
  mutating tools are stubbed at the adapter boundary and recorded, not
  executed. Ask-first behaviours (spoken reminders, proactive offers
  spoken aloud) are exercised through the text pipeline only — the
  harness never speaks, never sends, never books, never pays.

## Capabilities

### New Capabilities
- `dogfood-feedback-loop`: headless targeted-conversation batteries against the real respond pipeline, deterministic-first grading, a versioned labelled turn dataset, failure-to-eval promotion, draft lesson proposals, and a readiness scorecard

### Modified Capabilities
(none — batteries observe existing behaviour; the confirmation gate, scheduler, and offers arbiter are test subjects, never modified by the harness)

## Impact

- Orchestrator: new `dogfood/` package (batteries, runner, graders,
  dataset and scorecard writers) and a CLI entry point; runs on a
  schedule or on demand, entirely headless.
- In-repo data: `orchestrator/evals/dogfood/` — battery definitions,
  the labelled dataset (versioned JSONL + manifest), the promoted eval
  corpus, and the readiness scorecard. Synthetic conversations only:
  batteries never read the user's real memory, episodes, or finance
  data, so the dataset is safe to commit — this matters, it is the
  training set for `speech-act-addressee-classifier`.
- Builds on `text-chat-surface` (the respond seam it drives),
  `self-learning` (the lesson format it proposes into),
  `speaker-addressee` (bystander-confirmation scenarios exercise its
  binding), and `reminders-scheduler` (firing scenarios run its real
  scheduler against a fake clock).
- Out of scope, deliberately: any change to the systems under test;
  live dogfooding with real tools or real data (that remains the
  user's own usage); LoRA/DPO fine-tuning of a fallback LLM and
  PPO-style RL (considered and deferred — see the roadmap discussion in
  `speech-act-addressee-classifier`); and any learned component in the
  reminder scheduler's firing path, which stays deterministic forever.
- **Standing invariant, restated for this change:** the confirmation
  gate before irreversible actions stays rule-based permanently, with
  its zero-false-affirm eval bar. The harness grades that gate; it does
  not tune, train, or relax it.
