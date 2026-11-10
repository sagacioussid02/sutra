## ADDED Requirements

### Requirement: The classifier labels speech act and addressee locally
The system SHALL provide a classifier that, given a user turn's
transcript, returns a `speech_act` label (request / chat / rhetorical /
joke / aside) and an `addressee` label (sutra / other-person /
unclear), each with a confidence. Inference SHALL run locally with no
network call, and its p95 added latency per turn SHALL stay within the
budget for a Pi-class node stated in the eval report.

#### Scenario: A turn is classified
- **WHEN** a user turn is processed with the classifier enabled
- **THEN** the turn context carries both labels, their confidences, and the model version

#### Scenario: Classifier unavailable
- **WHEN** the model artefact is missing or inference fails
- **THEN** no hint is attached and turn processing continues exactly as without the classifier

### Requirement: Training data is the dogfood dataset, pinned by version
The classifier SHALL be trained only on the labelled dataset produced
by `dogfood-feedback-loop`, pinned to a dataset version recorded in the
training manifest. V1 SHALL NOT be trained until that dataset holds
roughly 500–1,000 labelled turns with every label represented at or
above the recorded per-label floor. Real household conversations and
external corpora SHALL NOT be used as training data.

#### Scenario: Dataset below the floor
- **WHEN** the pinned dataset version is below the per-label floor
- **THEN** training does not proceed and no model version is produced

### Requirement: The classifier is a soft hint, never a gate
Classifier output SHALL be advisory only. It SHALL NOT, by itself,
authorise or block a tool call, satisfy or block a confirmation, or
change the turn gate's rule from `speaker-addressee` (acting requires
*addressed*; speech addressed elsewhere never proceeds). The
orchestrator's existing judgements remain the decision-makers and MAY
consult the hint as one input among others.

#### Scenario: A wrong hint before an action
- **WHEN** the classifier labels an aside as a request addressed to Sutra and the existing judgement disagrees
- **THEN** the existing judgement governs and no action is taken on the hint's say-so

#### Scenario: Hint present for a confirmation reply
- **WHEN** a user turn replies to a pending confirmation
- **THEN** the confirmation is decided by the existing rule-based gate and classifier; the speech-act hint plays no part in the decision

### Requirement: Shipping requires beating the baseline on a held-out split
The dataset SHALL be split train / dev / held-out test by scenario,
never by turn. The baseline SHALL be the incumbent main-model
judgements scored over the same held-out turns with the same scorer.
The classifier SHALL ship only if, on the held-out split, it beats the
baseline overall and on the headline metric (the addressee
false-positive rate, defined in the design) and meets the latency
budget. Per-class accuracy SHALL be reported whether or not the bar
is met; a model that misses the bar SHALL NOT be enabled.

#### Scenario: Model beats averages but regresses on the headline metric
- **WHEN** the classifier's overall accuracy exceeds the baseline's but its addressee false-positive rate is worse
- **THEN** the model does not ship and the eval report records the negative result

#### Scenario: Split integrity
- **WHEN** the split is generated from a dataset version
- **THEN** no scenario contributes turns to more than one of train, dev, or held-out test

### Requirement: Model versions are reproducible and traceable
Each model version SHALL commit together: the artefact, the training
script version, the dataset version and split seed, and the eval report
including the baseline comparison and latency measurements. A retrained
model SHALL be a new version that must clear the same ship bar before
it can be enabled. The runtime SHALL record the model version on every
hint it emits.

#### Scenario: Retraining on a newer dataset
- **WHEN** a new model is trained on a later dataset version
- **THEN** it is committed as a new model version with its own eval report and remains disabled until it clears the bar

### Requirement: The confirmation gate stays rule-based
The confirmation gate before irreversible actions SHALL remain
rule-based permanently, held to its zero-false-affirm eval bar. The
classifier SHALL NOT be a component of that gate's decision. Any future
use of a learned signal as a soft second signal to the gate requires a
separate change and SHALL NOT lower the bar or replace the rules.

#### Scenario: Guard against gate creep
- **WHEN** the test suite runs
- **THEN** a guard test fails if any code path leads from the classifier package into the confirmation gate's decision, the scheduler, or tool authorisation
