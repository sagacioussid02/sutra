## Context

The user wants Sutra to look into things they care about while idle and tell them afterwards, conversationally, only when it is worth it. Everything needed exists: approved interests, the episode graph, a sandboxed research worker with budgets, and an offers system that judges, learns and delivers. This change joins them with the fewest new moving parts.

Constraints: web content is untrusted; the user's personal and financial matters must never reach a web search; spending must be bounded in code; findings are not memories; the user can see and stop everything.

## Goals / Non-Goals

**Goals:** pick a worthwhile topic without the user asking; run one bounded run; turn the result into a short dated summary; deliver through the offers system; learn which research the user values.

**Non-Goals:** other signal producers; acting on findings; research on anything the user has not approved or planned; a second delivery channel.

## Decisions

**1. Opt-in.** Idle research spends money and reads the web unsupervised, so it is off until the user turns it on (`/idle on`, or `SUTRA_IDLE_RESEARCH=on` as the starting default). The switch is stored in `idle.db` so a later `/idle off` wins over the environment.

**2. When it may run.** Only when all hold: switched on; interests, agents and offers are all available; the user has been quiet for at least the conversation idle gap (30 minutes, the graph's episode gap); no action awaits confirmation; no research or background job is running; today's idle cap and the minimum gap since the last idle run allow it; and the shared research allowance still leaves room for the user's own requests. The check runs every ten minutes and costs nothing when any condition fails.

**3. The picker.** One forced-schema, tools-off call. Input: numbered approved interests (label, how long since last researched, how the user reacted to earlier findings on it), numbered recent plans (graph nodes of mode `planned` or `decided` from the last 60 days, topic only), today's date, and the last ten research topics with dates. Output: `choice` (a number or 0), `brief`, `kind` (`whats_new`, `upcoming`, `compare`, `how_to`), `value` (0 to 1), `revisit_after_days`. It is told to prefer things that change with time (events, seasons, releases) and to return 0 when nothing is worth doing, which is the usual answer. Code validates the number, clamps `revisit_after_days` to 3 to 90 (the topic is not picked again before then), and applies the bar.

**4. The brief is checked in code.** The brief must be 20 to 200 characters, self-contained, and free of email addresses, phone numbers, long digit runs, currency amounts, URLs, and any word of the user's blocked topics. A brief that fails is dropped and the topic skipped for a day. Only the brief leaves the machine. Interest labels are the user's own words but general; the picker never sees a graph gist or any conversation text, so it cannot copy private detail into a brief.

**5. A learned bar for research.** A `research` bar (starting at 0.5) lives beside the offers bars. Outcomes of delivered findings move it by the same bounded steps: accepted lowers it, ignored or declined raises it. This makes Sutra research more of what is welcomed and less of what is not, without a fixed schedule for topics. The count and the gap are separate rails (decision 6).

**6. Rails are fixed and small.** `SUTRA_IDLE_DAILY_RUNS` (default 1), `SUTRA_IDLE_MIN_HOURS` (default 48, lower than first proposed at the user's request), a per-run budget narrower than a requested run's (2 searches, 3,000 tokens, 90 seconds; `SUTRA_IDLE_MAX_SEARCHES`, `SUTRA_IDLE_RUN_TOKENS`), and a reserve: an idle run does not start unless at least one of the day's research runs and a third of its tokens remain for the user. A failure or an empty result counts as a run and doubles the next gap. Shutdown cancels a run and records it as interrupted.

**7. The run reuses the sandbox.** The brief goes to the existing `AgentService.run`, tagged `idle:` in the task text so `/agents` can tell it apart. The worker's own limits (searches, tool calls, tokens, timeout) apply unchanged, and `SUTRA_AGENT_TOOLS` stays empty by default, so the run can only search the web.

**8. Summarising.** A tools-off call turns the findings into at most three short plain sentences, with the findings in an untrusted block and an instruction to ignore anything in them that reads like a command. Code prefixes "As of <date>:", caps the length at the signal limit, and strips web addresses. The full findings are kept (capped) in `idle.db` for `/idle show`; they are not memory.

**9. Delivery is a signal.** The summary becomes a signal with kind `research`, source `idle-research`, urgency `low`, expiry three days, and the interest label as the topic hint. The offers system judges it: connection to the graph, benefit against the bar, one at a time, daily rails, blocks. A `research` signal is always an ask: the teaser ("Something interesting turned up about Diwali events nearby, want to hear it?") says the topic and nothing else, and the summary is given only after yes, inside the untrusted block. An expired signal is dropped, so stale findings are never spoken. The topic already cleared the research bar when it was picked, and an approved interest counts as a connection to what the user cares about, so the judge decides only timing and interruption (offer, hold or drop) and no second benefit bar is applied to a finding. This came from a live run: with the ordinary bar, a finding on an approved interest scored 0.4 against 0.5 and would have been researched and never said.

**10. Learning back.** When the offer for a research signal is resolved, `OffersService` also records the outcome on the `research` bar. A decline on a topic also reduces that topic's chance to be picked again, through the existing per-topic outcome counts shown to the picker.

**11. Control and privacy.** `/idle` shows status, today's runs, the last runs (topic, outcome, when) and any waiting finding; `/idle on|off|now|show <id>|forget`. `/idle now` ignores quiet time (not budgets or blocks) so the path can be checked. Blocking a topic through offers also removes it from the picker's input. `idle.db` is owner-only and stores topic, brief, outcome and capped findings.

## Risks / Trade-offs

- [Spending on things nobody wants] → off by default, a one-run daily cap, a learned bar, and a reserve for the user's requests.
- [A brief leaking private detail] → the picker sees only approved labels and plan topics, and the brief is pattern-checked.
- [Prompt injection from web content] → findings are untrusted data, summarised with tools off, spoken only after yes and inside an untrusted block, and never saved to memory.
- [Stale findings] → dated "as of", expire in three days.
- [Quiet detection fooled by a long task] → running jobs and pending actions also block it, and nothing is said unprompted anyway: the result waits for the offers system.

## Open Questions

- The research bar and the 6-hour gap are guesses to tune with real use.
- Which interest kinds benefit most (events and releases versus evergreen topics) is left to the bar to learn.
