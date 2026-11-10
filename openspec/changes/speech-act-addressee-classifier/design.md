## Context

`speaker-addressee` (implemented, PR #10) gives Sutra the *rules* of
addressee: a deterministic pre-filter (no open conversation → nothing
is addressed), a tools-off main-model classifier call for
addressed / elsewhere / unclear, and an asymmetric turn gate that acts
only on *addressed*. A separate review of Sutra's rhetoric handling
found the gap this change addresses: there is no dedicated speech-act
layer — request vs chat vs rhetorical vs joke vs aside is whatever the
main model infers, from text, in the moment, unmeasurable and
unimprovable except by prompt edits.

Meanwhile `dogfood-feedback-loop` produces exactly what a learned
classifier needs and what prompt engineering can never have: hundreds
of turns whose intended speech act and addressee are known because the
scenarios authored them, versioned in-repo.

The roadmap decision this design encodes: Sutra's big brain stays
rented and frozen; gradient learning enters only where Sutra owns a
small model outright, on a narrow job, behind an eval bar, in an
advisory role. This classifier is the template for that pattern.

## Goals / Non-Goals

**Goals:**
- A local, fast, measurable speech-act + addressee signal on every
  turn.
- Improvement that is *demonstrated*: beat the main-model baseline on
  held-out data, on the error that matters most, or don't ship.
- A training pipeline that is reproducible from committed artefacts:
  dataset version + script + seed → model + eval report.
- Zero change to any safety rule: gates, confirmations, and the
  scheduler behave identically whether the hint is present, absent, or
  wrong.

**Non-Goals:**
- Deciding anything. The classifier advises; the orchestrator's
  existing judgements and gates decide.
- Audio understanding. Transcript in, labels out — tone-from-audio is a
  different change against real hardware.
- Personalisation to real household speech. Training data is the
  synthetic dogfood dataset; fine-tuning on the user's real
  conversations is out of scope and would need its own privacy design.
- Beating the baseline by construction. If the main model is better,
  the honest outcome of this change is a negative result and no model
  in the live path.

## Decisions

### Two label heads, one small model
One model, two outputs: `speech_act` (request / chat / rhetorical /
joke / aside) and `addressee` (sutra / other-person / unclear), each
with a confidence. The label sets are exactly the dogfood dataset's
labels, so training and eval need no mapping layer. Architecture is
deliberately boring: a small supervised text classifier (fine-tuned
tiny transformer or a linear model over n-gram/embeddings features —
chosen at implementation time against the latency budget, recorded in
the training manifest). Bigger architectures need a justification
measured against the bar, not enthusiasm.

*Why one model:* the labels are correlated (an aside is usually
other-person; a rhetorical question is usually chat) and the deployment
budget is one inference per turn on a Pi-class node. Two models double
the footprint for a distinction the features don't respect.

### Advisory plumbing: the hint rides the turn context
The orchestrator runs the classifier on each user turn (when enabled)
and attaches `{speech_act, addressee, confidences, model_version}` to
the turn context. The addressee judgement in `speaker-addressee` may
take it as an input feature; the main prompt may include it as a
labelled hint. Nothing downstream is required to obey it, and removing
the model (feature off, artefact missing, inference error) returns the
system to exactly today's behaviour.

*Why:* this is the soft-hint contract from the classifier review —
a learned signal earns influence by being useful inside existing
judgements, never by holding a veto. It also makes the model safely
deletable, which is the correct default trust level for a v1 learned
component.

### The eval split is by scenario, and the baseline is the incumbent
Train / dev / held-out splits partition *scenarios*, never individual
turns: turns from one scenario share templates and phrasing, so a
per-turn split would leak the test set into training and flatter the
model. The baseline is the incumbent behaviour — the main-model
addressee judgement, plus main-model speech-act labels elicited with a
fixed prompt — run over the identical held-out turns. Both are scored
with the same code, in the same report.

*Why:* the decision this eval supports is "replace the incumbent's
unaided judgement with incumbent + hint". The only honest comparison is
same turns, same scorer, incumbent measured rather than assumed.

### The headline metric is the expensive error
Report per-class accuracy for all labels, but the ship bar keys on the
addressee false-positive rate: turns whose true addressee is
other-person, or whose true speech act is aside, that the pipeline
reads as a request addressed to Sutra. That error is the one that makes
Sutra act on speech never meant for it — the failure the whole
addressee design exists to prevent. The classifier ships only if it
beats the baseline overall *and* on this metric; ties or regressions on
the headline metric mean no ship, whatever the averages say.

### Local inference with a hard latency budget
The model runs in-process or as a local sidecar on the same node, no
network. Budget: p95 added latency per turn small enough to be
invisible in conversation (target ≤ 50 ms on a Pi-class node,
confirmed by measurement in the eval report, not assumed). If the
chosen architecture misses the budget on the target hardware class, it
misses the bar.

### Versioning ties model, data, and verdict together
Each trained model version commits: the artefact, the training script
version, the dataset version and split seed, and the eval report
(baseline comparison, per-class tables, headline metric, latency
measurements). The runtime records the model version on every hint, so
any later behaviour question — "why did it read that as a joke?" — can
be traced to an exact model and dataset.

## Risks / Trade-offs

- [Dataset is synthetic; the household is not] → the classifier is a
  hint, not a gate, precisely so distribution shift degrades it to
  noise inside a judgement that still works. Revisit personalisation
  only with real usage evidence and its own change.
- [Labels encode the battery authors' theory of speech acts] → the
  baseline comparison is the guard: if the theory is wrong, the
  incumbent wins and nothing ships. Label definitions live with the
  dataset in `dogfood-feedback-loop`.
- [A confident wrong hint biases the main model] → confidences travel
  with the hint and the prompt presents it as fallible; the dogfood
  batteries, which exercise the assembled system, would catch a
  systematic bias as a scorecard regression.
- [Small model becomes unmaintained weight] → feature-flagged, one
  package, deletable without behaviour change (Decision 2). If a future
  dataset version makes it stale and nobody retrains, the correct state
  is off, and the system is whole without it.
- [Pressure to let it gate "just confirmations, it's accurate"] →
  refused in the spec, permanently: accuracy on a held-out synthetic
  split is not a safety case, and the confirmation gate's zero-false-
  affirm bar belongs to rules that can be read, not weights that can
  only be measured.

## Migration Plan

Ships behind a switch, default off, and only after the eval bar is met
and the report committed. Enabling is a config change; disabling or
deleting the artefact restores prior behaviour byte-for-byte in every
gate. Retraining never auto-deploys: a new model version is a new PR
with its eval report, reviewed like code.

## Open Questions

- Architecture choice (tiny fine-tuned transformer vs linear model over
  embeddings) — decide on the first training run by accuracy-per-
  millisecond on Pi-class hardware; the spec's budgets and bars are
  architecture-neutral.
- Threshold for "roughly 500–1,000 turns": the real trigger should be
  per-label minimums (every speech-act and addressee label with enough
  held-out examples to measure), not a raw total. Set the per-label
  floor when the dataset's label distribution is known.
