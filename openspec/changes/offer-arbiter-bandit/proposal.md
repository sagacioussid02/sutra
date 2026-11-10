## Why

The proactive-offer arbiter (`proactive-offers`, with effort estimates
and deferral from the principal-state extension to `world-state`)
decides what Sutra may surface using rules: caps, a daily budget, no
offers while a confirmation is pending, declared capacity and
commitments. Rules are the right *constraints*. They are a poor
*ranking*: which of the five permissible offers is actually worth this
person's attention, on this kind of day, is something the rules cannot
know and the user keeps teaching by behaviour — accepting this kind,
deferring that kind, dismissing the other on sight. Today that teaching
evaporates; `self-learning` can turn heavy patterns into proposed
lessons, but the arbiter itself ranks the same on day 90 as day 1.

This is step 3 of the gradient-learning roadmap, and the one place
genuine reinforcement learning fits Sutra: a contextual bandit over the
arbiter's *already-permitted* choices, learning from the user's
explicit outcomes. The bandit's world is deliberately tiny — rank what
the rules allowed, learn from what the user did — which is why it is
safe to let it learn at all.

## What Changes

- **A bandit layer inside the arbiter's decision.** When the existing
  rules produce a set of permissible offers, the bandit ranks them
  (including "surface nothing now" as an arm) using context features,
  and the top choice within the rules is what surfaces. The bandit
  never widens the permissible set: anything the rules exclude stays
  excluded, whatever the bandit believes.
- **Reward is explicit user outcome only.** Accept = positive, defer =
  mildly positive (right offer, wrong time is information, not
  failure), dismiss = negative. No inferred engagement: no learning
  from silence, dwell, conversation length, or whether the user
  happened to be nearby. An offer that expires unanswered teaches
  nothing and is recorded as no-outcome, not as a rejection.
- **Context is declared state only.** Features come from the
  principal-state / `world-state` declared fields (capacity,
  commitments, time of day and day type, offer kind, effort estimate,
  recent outcome history per kind). No inferred personal attributes —
  no mood, no health, no inferred relationships — as features, ever.
  If a field is not something the user declared or the system recorded
  as an outcome, it is not a feature.
- **Hard constraints stay hard and stay outside the bandit.** The
  existing caps (per-day and per-kind), the "no offers while a
  confirmation is pending" rule, quiet hours and their equivalents,
  and lesson `block` effects from `self-learning` are evaluated before
  and after the bandit exactly as today. The bandit cannot override,
  relax, or route around any of them; a constraint change is a normal
  reviewed change, not something learning can reach.
- **Cold start is today's behaviour.** Until a minimum number of
  recorded outcomes (a configured threshold, on the order of dozens per
  the design) has accumulated, the arbiter behaves exactly as it does
  now — rule-based ranking — and the bandit only observes and logs what
  it *would* have ranked. Activation past the threshold is a config
  step, visible in the control surface, not a silent flip.
- **Every decision is explainable.** The arbiter logs, per decision:
  the permissible set the rules produced, the context features used,
  the bandit's ranking and the outcome later recorded. "Why was I shown
  this?" is answerable from the episode record in plain terms — the
  rules that allowed it, the context that ranked it first, and the
  past outcomes that taught that.
- Out of scope, deliberately: learning *whether* an offer may exist
  (generation stays with the offers system and its sources); new offer
  kinds; any change to caps or pending-confirmation rules; cross-user
  learning (one user's outcomes never train another's bandit — with
  `per-user-identity`, the bandit is per-user); and any bandit
  influence on confirmations, reminders, or tool calls — offers only.

## Capabilities

### New Capabilities
- `offer-arbiter-bandit`: a per-user contextual bandit that ranks the proactive arbiter's rule-permitted offers from explicit accept / defer / dismiss outcomes, under the arbiter's unchanged hard constraints, with full decision logging

### Modified Capabilities
(none — `proactive-offers`' caps, pending-confirmation block, and deferral behaviour are unchanged and remain the constraint layer this change ranks within)

## Impact

- Orchestrator: the offers arbiter gains a ranking stage and an
  outcomes store (local, per-user, owner-only, gitignored like other
  personal stores); the episode record gains the decision log this
  change specifies. No gateway, twin, or finanxe changes.
- Depends on real usage: activation requires outcome data, which only
  exists once the dogfood loop (`dogfood-feedback-loop`) is running
  and, mainly, once Sutra is in live use. The observation-only mode can
  ship earlier; the learning mode cannot be meaningfully evaluated
  before the outcomes exist, and this change says so rather than
  pretending simulation substitutes.
- Builds on `episode-graph-offers` / `proactive-offers` (the arbiter),
  `world-state` principal-state (the declared context fields), and
  `self-learning` (whose `block` lessons remain a hard constraint the
  bandit respects; the two learning systems coexist — lessons are the
  user's explicit steering, the bandit is ranking within it).
- **Standing invariant, noted for this change:** the confirmation gate
  is outside this change entirely. The bandit ranks offers; it has no
  path to confirmations, which stay rule-based permanently with their
  zero-false-affirm eval bar, and no offer outcome is ever treated as
  evidence about them.
