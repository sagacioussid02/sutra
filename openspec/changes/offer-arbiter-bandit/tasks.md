## 1. Outcome store and decision log

- [ ] 1.1 Add the per-user outcomes store (local, owner-only, gitignored): per decision — timestamp, permissible offer set (ids, kinds), constraint outcomes, feature vector, arm scores, chosen arm; outcomes (accept / defer / dismiss) appended to the same record when they resolve; expired offers recorded as no-outcome
- [ ] 1.2 Wire outcome recording to the existing offer resolution path so every surfaced offer's verdict lands on its decision record exactly once
- [ ] 1.3 Tests: an accepted, a deferred, and a dismissed offer each update their decision record; an expired offer records no-outcome and produces no reward; stores for two user ids never mix

## 2. Feature builder (declared state only)

- [ ] 2.1 Implement the feature builder over the allowlist only: offer kind and source, effort estimate, time of day / day type, declared capacity and active commitments from principal-state (`world-state`), trailing per-kind outcome counts
- [ ] 2.2 Add a test asserting the built feature vector contains only allowlisted fields (a new candidate field fails the suite until the allowlist in the spec is amended)
- [ ] 2.3 Tests: no feature is derived from conversation content, inferred state, or any other person's data

## 3. Bandit ranking stage

- [ ] 3.1 Implement the ranking stage in the arbiter pipeline at the fixed position: after all hard constraints (caps, pending-confirmation block, quiet rules, lesson `block` effects, capacity) and before surfacing; its input is only the permitted set plus a "surface nothing" arm
- [ ] 3.2 Implement the bandit (algorithm chosen at implementation and recorded in the change notes) with the fixed reward mapping (accept +1, defer +0.3 with time context, dismiss −1, expired = no update) as a constant in code
- [ ] 3.3 Bounded exploration: rate decays with per-kind outcome counts to a configured floor; ties and high uncertainty break toward surfacing nothing
- [ ] 3.4 Tests: an offer excluded by any hard constraint can never be surfaced by the bandit, including under exploration; while a confirmation is pending, the stage is never reached; a `self-learning` block on a kind removes it before ranking

## 4. Cold start and activation

- [ ] 4.1 Observe-only mode: below the activation threshold (overall and per-kind outcome minimums in config), ranking is today's rule-based order and the bandit writes shadow rankings to the decision log
- [ ] 4.2 Activation: a config flag, shown on the control surface with the outcome counts behind it; activation is a deliberate step, never automatic at threshold
- [ ] 4.3 Feature switch for the whole change, off by default; document every new `SUTRA_*` variable in `orchestrator/.env.example`
- [ ] 4.4 Tests: with the switch off or below threshold, arbiter behaviour is byte-identical to today apart from logging; deleting the outcomes store returns the bandit to cold start

## 5. Explainability

- [ ] 5.1 Add the "why was I shown this?" view over the decision log (episode record / control surface): the constraints that permitted the offer, the context features that ranked it first, and the past outcomes that most influenced the ranking, in plain language
- [ ] 5.2 Tests: every surfaced offer under an active bandit has a complete decision record sufficient to render the explanation; shadow decisions are marked as shadow

## 6. Docs and verification

- [ ] 6.1 README section: what the bandit learns and from what, the fixed reward mapping, the constraint fence, cold start and activation, how to disable it or reset it (delete the store), and the standing invariant — confirmations are outside this system entirely and stay rule-based with their zero-false-affirm bar
- [ ] 6.2 Manual check (requires live use): after activation in real use, review a week of decision logs — every surfaced offer explainable, no constraint ever bent, dismissal rate per kind visibly moving or an honest note that it is not
