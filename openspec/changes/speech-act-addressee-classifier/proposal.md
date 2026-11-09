## Why

Sutra has no dedicated understanding of *what kind of turn it just
heard*. The `speaker-addressee` change shipped the gate — speech
addressed elsewhere never acts, unclear never acts — but the judgement
behind it is the main model reading the transcript: capable, but a
rented brain doing a narrow job on every turn, with latency and cost to
match, and no way to improve it except prompt edits. It also sees text
only: it cannot learn, from accumulated examples, how this household's
sarcasm, asides, and half-sentences to another person actually sound.

This is step 2 of the gradient-learning roadmap, and it is the right
first thing to gradient-train: a narrow classification job, a local
model small enough for a Pi-class node, and — once
`dogfood-feedback-loop` has run — a labelled dataset to train and,
just as importantly, to *judge* it against. The classifier earns its
place by beating the current main-model judgement on a held-out split,
or it does not ship.

## What Changes

- **A small local classifier for speech act and addressee.** Each user
  turn is labelled `speech_act` ∈ {request, chat, rhetorical, joke,
  aside} and `addressee` ∈ {sutra, other-person, unclear}, with
  confidences. The model runs locally (no network call), inside a
  latency budget suitable for a Pi-class node, and is small enough to
  ship in-repo alongside its training script.
- **Trained only on the dogfood dataset.** Training data is the
  labelled turn dataset produced by `dogfood-feedback-loop`, pinned to
  a dataset version in the training run's manifest. No hand-labelled
  side sets, no external corpora, no real household conversations. V1
  is trained only once the dataset holds roughly 500–1,000 labelled
  turns with every label represented; below that, the change waits.
- **A soft hint, never a gate.** The classifier's output is passed to
  the orchestrator as an advisory signal alongside the existing
  judgements: it may inform the addressee decision in
  `speaker-addressee` and the main model's reading of a turn. It SHALL
  NOT gate anything by itself. Specifically and permanently: it never
  decides a confirmation, never authorises or blocks a tool call, and
  the turn gate's asymmetric rule (acting requires *addressed*;
  elsewhere never proceeds) is unchanged and remains the orchestrator's,
  not the classifier's.
- **An eval protocol with a ship bar.** The dataset is split —
  train / dev / held-out test — by scenario, not by turn, so near-
  duplicate turns from one scenario cannot leak across the split. The
  baseline is the current main-model judgement run over the same
  held-out turns. The classifier ships only if, on the held-out split,
  it beats that baseline overall *and* on the headline metric: the
  addressee false-positive rate — turns truly addressed to another
  person (or asides) that are read as addressed to Sutra with
  request intent — must be lower than the baseline's, because acting on
  speech that was never for Sutra is the expensive error. Per-class
  accuracy for every speech-act and addressee label is reported either
  way; a model that misses the bar is a report, not a deployment.
- **Versioned and reproducible.** Model artefact, training script,
  dataset version, split seed, and the eval report are committed
  together; retraining on a newer dataset version produces a new model
  version with its own eval report, and shipping a retrained model
  requires re-clearing the same bar.
- Out of scope, deliberately: audio features or tone-from-voice (the
  classifier reads the transcript, like everything else today);
  speaker *identification* (that is `speaker-addressee`'s signal, a
  different job); replacing the main-model addressee judgement (the
  classifier advises it); any use of the classifier in the reminder
  scheduler's firing path (deterministic forever); and LoRA/DPO
  fine-tuning of a fallback LLM or PPO-style RL — deferred by the
  roadmap, not smuggled in here.

## Capabilities

### New Capabilities
- `speech-act-addressee-classifier`: a locally run, supervised classifier over turn transcripts producing speech-act and addressee labels with confidences, trained on the dogfood dataset and consumed by the orchestrator as an advisory hint only

### Modified Capabilities
(none — `speaker-addressee`'s gate and rules are unchanged; this change adds an input signal the existing judgement may consult)

## Impact

- Orchestrator: a new `classifiers/` package (model artefact, loader,
  training script under `orchestrator/training/`), the hint attached to
  the turn context where the addressee judgement and the main prompt
  can consult it, and the eval runner under `orchestrator/evals/`.
- Depends on `dogfood-feedback-loop` (the dataset, its labels, its
  versioning) and builds on `speaker-addressee` (whose gate consumes —
  but is never replaced by — the hint).
- Runtime cost when shipped: one small local inference per turn, inside
  the latency budget in the spec; no new network calls, no new personal
  data (training data is synthetic by construction).
- **Standing invariant, restated for this change:** the confirmation
  gate before irreversible actions stays rule-based permanently, with
  its zero-false-affirm eval bar. This classifier is explicitly
  forbidden from that gate: it may one day advise the gate as a soft
  second signal through a separate change, but it never replaces the
  rules and never lowers the bar.
