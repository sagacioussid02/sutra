## Context

The offers pipeline today: sources (episode graph, idle research,
life follow-ups, lesson proposals) generate candidate offers; the
arbiter in `proactive-offers` filters and ranks them under declared
constraints — per-day and per-kind caps, nothing while a confirmation
is pending, principal-state capacity/commitments and effort estimates
from `world-state`, and `self-learning` `block` lessons. What surfaces
is, within those rules, essentially first-come or statically ordered.

The user's outcomes are already recorded (offers resolve as accepted,
deferred, dismissed, or expired) — the episode record has them. What is
missing is any mechanism that lets those outcomes change future ranking,
short of the user approving a lesson. A contextual bandit is the
standard, bounded tool for exactly this: repeated choices among a small
set of arms, context per choice, reward per outcome, exploration kept
on a leash.

This change is step 3 of the gradient-learning roadmap deliberately:
it needs what steps 1–2 do not produce — real outcomes from real use —
and it is sequenced last so nobody is tempted to evaluate it on
simulated preferences.

## Goals / Non-Goals

**Goals:**
- Ranking that visibly improves from the user's own outcomes: fewer
  dismissed-on-sight offers, better timing, without any increase in
  total offer volume.
- Learning that is provably fenced: the bandit ranks a set the rules
  already permitted, under constraints it cannot touch.
- An explanation for every surfaced offer, retrievable in plain terms.
- A cold start indistinguishable from today, and an off switch that
  returns to today exactly.

**Non-Goals:**
- Deciding what may be offered. Generation and permissibility are the
  existing system's; the bandit only orders the permitted set
  (including choosing "not now").
- Inferring anything about the user. Features are declared state and
  recorded outcomes only — this is the principal-state posture
  (declared-only) applied to learning.
- Optimising engagement. The reward is the user's explicit verdict on
  an offer, not attention; a bandit that learned to be clicked would
  be a dark pattern with good maths.
- Sharing learning across users. Per-user bandits, per-user stores;
  `per-user-identity` keeps them separate.

## Decisions

### The bandit sits between the rules and the surface, and sees only the permitted set
Pipeline order is fixed: sources generate → hard constraints filter
(caps, pending-confirmation block, quiet rules, lesson blocks,
capacity) → bandit ranks the survivors plus a "surface nothing" arm →
the winner surfaces → outcome is recorded against the decision log.
The bandit never sees filtered-out offers, so it cannot learn to want
them, and exploration can only ever choose among permitted offers or
silence.

*Why:* this ordering is the whole safety case. A learned component
downstream of deterministic constraints inherits their guarantees; one
upstream of them would have to re-prove them.

### Reward mapping is fixed and legible
Accept: +1. Defer: +0.3 and recorded with its time context, since defer
means "not now" — the bandit should learn timing from it, not treat it
as failure. Dismiss: −1. Expired unanswered: no update (absence of a
verdict is not a verdict). The mapping is a constant in code, visible
in the decision log, and changing it is a reviewed change, not a tuned
hyperparameter discovered by the system.

*Why:* reward design is where bandits quietly become manipulative. A
small, fixed, human-readable mapping keeps the objective auditable:
"show offers this user tends to accept, at times they tend to accept
them".

### Context features are an allowlist, drawn from declared state
Permitted features: offer kind and source; effort estimate; time of
day / day type; declared capacity and active commitments from
principal-state; counts of recent outcomes per kind (accepts, defers,
dismisses over a trailing window). Anything not on the allowlist is not
a feature — the feature builder takes only these fields, and a test
asserts the built feature vector contains nothing else. Inferred
attributes (mood, health, busyness inferred from behaviour rather than
declared, anything about other people) are excluded by construction,
not by policy note.

### Exploration is bounded and shrinks
A standard contextual bandit (LinUCB or Thompson sampling over a small
linear model — chosen at implementation, recorded in the change notes)
with an exploration rate that starts modest and decays as outcomes per
kind accumulate, floored at a small value so a changed taste is still
discoverable. Exploration never applies to the "surface nothing" arm's
*opposite*: when the bandit is uncertain, ties break toward silence,
because an offer not shown costs less than an offer dismissed.

### Cold start: observe-only until the threshold, then a visible activation
Below the minimum outcome count (default 50 recorded outcomes overall,
with at least a handful per active offer kind — exact numbers set in
config and recorded when activated), the arbiter ranks by today's rules
and the bandit logs shadow rankings ("would have ranked X first").
Shadow logs make activation reviewable: the user (or a review) can see
whether the bandit's taste looks sane before it drives anything.
Activation is a config flag, shown on the control surface with the
outcome count that justified it.

### Decision logging is part of the feature, not debug output
Per decision, the log records: timestamp, the permissible set (offer
ids and kinds), the feature vector, each arm's score, the chosen arm,
the constraint outcomes that produced the set, and — appended when it
happens — the user outcome. The episode record surfaces this as the
answer to "why was I shown this?": rules that allowed it, context that
ranked it, outcomes that taught it, in that order. Logs are local,
per-user, and deletable; deleting the outcomes store resets the bandit
to cold start.

## Risks / Trade-offs

- [Feedback loop narrows Sutra's world] → a bandit that only learns
  from shown offers stops exploring kinds the user might now like:
  exploration floor, per-kind outcome windows that age out, and
  "surface nothing" never becomes the only learned answer because
  accepts keep positive reward flowing to shown kinds.
- [Defer-farming: bandit learns to offer only sure things] → accepted
  as partially fine (sure things are what offers should be), bounded
  by the exploration floor and by sources continuing to generate
  variety the rules permit.
- [Reward hacking via timing] → the bandit could learn to offer when
  the user is too busy to dismiss, reading expiry as neutral:
  expiries are excluded from reward, and the decision log makes a
  timing pattern visible; if observed, the reviewed fix is to score
  repeated expiries per kind as a soft negative — noted here as the
  known remedy, not implemented speculatively.
- [Two learning systems fight] → `self-learning` lessons are explicit
  user steering and win: a `block` lesson removes its kind from the
  permissible set before the bandit runs, and an approved guidance
  lesson outranks bandit preference wherever both speak. The bandit is
  the junior system by design.
- [Small data, confident model] → the activation threshold, shadow
  mode, and decay-toward-silence tie-breaking exist for this; the
  bandit's scores are also capped in influence by the fact that it only
  reorders a small permitted set — the blast radius of a wrong ranking
  is a worse-ordered handful of already-allowed offers.

## Migration Plan

Ships in observe-only mode behind a switch, default off. With the
switch on and below threshold: today's ranking, shadow logs
accumulating. Activation past threshold is a deliberate config step by
the user. Turning the switch off restores rule-based ranking exactly;
the outcomes store remains (it is also the episode record) but is
ignored. No migration of existing offers data is needed — outcome
recording already exists; this change begins consuming it.

## Open Questions

- Algorithm choice (LinUCB vs Thompson sampling) — decide at
  implementation on simplicity and debuggability of the decision log;
  the spec's constraints (allowlisted features, fixed reward, bounded
  exploration) are algorithm-neutral.
- Threshold numbers (50 overall, per-kind minimums) are placeholders
  with the right shape; set them from the real outcome rate once live
  use shows how many offers a week actually resolve.
- Should deferral *target time* (when the user deferred to) be a
  feature? It is declared by the deferral itself, so it fits the
  allowlist philosophy; add only if the decision logs show timing is
  where the ranking is losing.
