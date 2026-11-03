## 1. Graph storage and episodes

- [x] 1.1 `graph/db.py`, `store.py`: owner-only versioned SQLite for nodes (topic, gist, mode, open items, entities, weight, status, timestamps) and edges (type, strength, reason, weight)
- [x] 1.2 Episode closing (subject change or idle gap) and a forced-schema summariser call; exclusion rules (excluded tools contribute nothing, tool-using turns count only the user's words, low-confidence skipped)
- [x] 1.3 Tests: node written from an explanation; excluded and tool turns; low confidence; no full reply or utterance stored; owner-only file

## 2. Linking and retrieval

- [x] 2.1 `Retriever` interface with the lexical implementation: overlap, recency, one-hop neighbours, prompt-size bound
- [x] 2.2 Linker subagent (forced schema, tools off), edge validation, merge on strong `same_topic`
- [x] 2.3 Decay and archive, node cap; `/graph` commands; `SUTRA_GRAPH` switch
- [x] 2.4 Tests: neighbour widening, nothing found makes no call, invalid edges discarded, merge, decay, forget

## 3. Relatedness advice

- [x] 3.1 Advice subagent: current and previous two user utterances, numbered candidates with open items, age and past outcomes; validation; subject-change test so one subject is checked once
- [x] 3.2 Tests: tool-calling then agent-building gives advice; weekend plans gives none; invalid node is none; same subject makes one call; no call without candidates

## 4. Judge, bars, arbiter

- [x] 4.1 `offers/db.py`, `store.py`: offers with outcome, kind, topic, local hour, judge reason; bars; blocks; signals; daily counters
- [x] 4.2 Judge call (forced schema) with clamped retry time and stored reason
- [x] 4.3 Bars: bounded steps per outcome, drift to start, limits; blocks for explicit stops
- [x] 4.4 Arbiter: one item per turn, ordering, pending action and open offer, blocks, daily rail and call rail; interests nudge permission hook
- [x] 4.5 Tests: bar moves up and down within limits and drifts back; a block is permanent; one at a time; rail binds for ordinary but not urgent; nudge defers to a follow-up

## 5. Offer, answer, delivery

- [x] 5.1 Orchestrator: validated offer appended to the finished reply, counted when appended, no interests nudge on that turn, soft offer slot
- [x] 5.2 Next-turn handling: phrase check, then classifier; accepted, deferred, declined, ignored; slot cleared after one turn; outcomes feed the bars
- [x] 5.3 Grounded delivery note; mark the open item done
- [x] 5.4 Tests: yes, not now, no, off-topic reply, lingering offer does not capture a later yes, request and tool calls run normally with the offer last

## 6. Timely offers

- [x] 6.1 Signal intake in the offers store and a producer-allowlisted urgent path; expiry drop
- [x] 6.2 Judging with the graph neighbourhood for the summary and hint; higher bar when unconnected
- [x] 6.3 Voice: spoken at a quiet moment through the notice mechanism, `tell` or `ask` teaser chosen by the judge, never interrupting; text: held for the next reply; code checks that a `tell` carries no action
- [x] 6.4 A development command to inject a signal for verification
- [x] 6.5 Tests: warning tied to a stated plan is offered; unconnected minor signal held or dropped; expired signal never spoken; unlisted producer cannot be urgent; weather defaults to medium; safety alert is a `tell`; an ignored `tell` raises the bar

## 7. Control, config, docs, verification

- [x] 7.1 `/offers` commands and `stop_offers` tool; `SUTRA_OFFERS`; voice low-confidence flag passed to `respond`
- [x] 7.2 Config: `SUTRA_GRAPH`, `SUTRA_OFFERS`, `SUTRA_OFFERS_DAILY_MAX`, `SUTRA_OFFERS_CALLS`, `SUTRA_GRAPH_DIR`, `SUTRA_OFFERS_DIR`, urgent-producer allowlist; README section
- [x] 7.3 Manual check with a real key: ask a "how does X work" question, move stored times forward, ask something related and judge the advice, offer and example; inject a snow signal after a mountain-driving episode and judge the heads-up
