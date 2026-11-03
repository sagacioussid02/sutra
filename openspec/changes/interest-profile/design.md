## Context

Episodes already hold every user utterance with a timestamp and the names of the tools used. Memories hold durable statements and have a reviewable proposal path (`/approve`, `/reject`). What is missing is a topic-level view and a way to use it gently in conversation.

Constraints: the user talks about personal things; financial turns must not feed inference; the user must be able to see why Sutra believes something and delete it; unprompted speech must ask first (a standing project rule); cost must stay tiny.

## Goals / Non-Goals

**Goals:**
- Derive candidate interest topics from the user's own words, with evidence they can read.
- Use only topics the user approved.
- Let the assistant connect topics naturally in conversation, rarely.
- Keep it separate from the memory store so each can change independently.

**Non-Goals:**
- Speaking unprompted, scheduled research, or acting on interests (`idle-research`).
- Learning from feedback signals (`self-learning`).
- Embeddings or a vector store. Topics are short labels compared by word overlap, which is enough at this size.
- Inferring anything about people other than the user.

## Decisions

**1. A separate component and database.** Interests live in `interests.db`, not in `memory.db`. The memory table's `kind` column is a CHECK constraint, so a new kind would mean rebuilding the table and bumping its schema; a separate file avoids touching what already works and keeps the two concerns independent. The user still sees one consistent set of controls. Alternative: a new memory kind. Rejected for the migration risk and the coupling.

**2. Reflection reads a narrow, filtered slice.** `SqliteMemory.recent_user_episodes(since, limit)` returns `(id, ts, utterance, tool_names)` only. The reflection step drops episodes that used any tool whose name starts with a configured excluded prefix (default `finanxe_`), drops trivial replies ("yes", "no"), truncates each utterance to 200 characters, and caps the batch at 150 utterances over the last 30 days. Replies and tool results are never read: replies may contain money figures and tool results are untrusted. Only hot episodes are used, so archived history is never touched.

**3. A forced-schema model call proposes topics and changes.** The model is shown the numbered utterances as data, plus the interests already known (numbered, label only, any status). It must call `record_interests`, returning up to three items, each with a short label (at most 60 characters), a spoken phrasing, the numbers of supporting utterances, and a `relation`: `new`, `strengthens` (naming a known interest), or `changes` (naming a known interest, with a one-line `before` and `now`). Known interests are shown so it can recognise change; they carry no evidence text and no replies. The prompt asks for deliberately expressed or repeated interests (trips they are planning, hobbies, things they follow), not one-off lookups or chores, and says the utterances are data, not instructions. Alternative: cluster by embeddings. Rejected: extra dependency and cost for little gain at this scale.

**4. Code validates the model's output.** Evidence numbers must refer to utterances that were actually sent; invalid ones are dropped and a topic with none left is discarded. A `strengthens` or `changes` item must name an interest that exists and is not rejected, or it is treated as `new`. A `changes` item whose `before` does not match the named interest's label by word overlap is demoted to `new`, so the model cannot rewrite an interest it did not actually see change. Strength and recency are computed by code from the evidence timestamps, never taken from the model. A new topic is compared by word overlap to every existing interest in any status, including rejected, so duplicates and declined topics do not come back; a match with an existing interest adds evidence to it instead of creating a second one.

**5. Everything starts as `proposed`; changes are revisions.** Statuses are `proposed`, `active`, `rejected`, `muted`, `superseded`. Only `active` interests are ever shown to the conversation model. The user approves or rejects with `/interests approve|reject <id>` or, by voice, with a yes or no to an ask-first offer ("I've noticed you've been looking into weekend trips. Want me to keep that in mind?"). Manually added interests (`/interests add <topic>`) are `active` at once because the user wrote them.

A `changes` item creates a new `proposed` interest linked to the old one, with the before and now text. Approving it makes the new one `active` and the old one `superseded`; the old one stays in the history shown by `/interests history <id>`. Rejecting it leaves the old interest exactly as it was, and the same change is not proposed again.

Quiet interests: an active interest with no new evidence for 90 days becomes dormant and is left out of the prompt block, without being deleted. The user is asked once, later, whether they are still into it. Yes refreshes it, no mutes it, and "not now" leaves it dormant with no further asking until new evidence appears.

**5a. Telling the user later.** Revisions and check-ins are never raised in the middle of a conversation. They wait in the store as pending offers and are announced the same way as new proposals (decision 9): one at a time, only at a quiet moment, only as a question. Pending offers survive restarts.

**5b. Facts versus tastes.** A stated fact that changes is already handled by the memory store's supersession and its "Updated: ... (replacing ...)" notice, so reflection does not re-derive facts. Memory contents are not fed to reflection, because user-stated facts can be financial or personal in ways the excluded-tool rule would not catch.

**6. Resurfacing is a prompt block with a code-enforced cap.** Each turn, if the interest feature is on and there are active interests, the orchestrator appends a labelled block: today's date and up to eight interests. On at most one turn per `SUTRA_NUDGE_HOURS` (default 24, persisted so restarts do not reset it) the block also carries a note allowing the assistant to connect the current topic to an interest, briefly and only if natural, never stating event dates as fact, and offering a lookup through the research tool instead. The cap counts the turn the note was offered, whether or not the model used it, which errs on the side of fewer nudges. The block says interests are information, not instructions. Alternative: a separate model call to decide relevance. Rejected: doubles per-turn cost; the main model already sees the conversation.

**7. Muting by voice.** A local tool `mute_interest(topic)` lets the model respond to "stop bringing that up". It only ever reduces behaviour (sets `muted`), so it needs no confirmation, but it matches by topic text against active interests only and reports what it muted.

**8. When reflection runs.** In-process: a due-check at startup and then hourly. It runs if reflection is on, at least `SUTRA_REFLECTION_HOURS` (default 24) have passed since the last run, and there is at least one new eligible utterance since then. One run at a time, failures are logged and retried at the next due-check, and each run is recorded (time, utterances read, topics proposed). `/interests reflect` runs it on demand. Alternative: hook into the reminders scheduler. Rejected: that scheduler is a reminder poll loop, not a general job runner, and generalising it is a larger change than this needs.

**9. Surfacing proposals.** At most one proposal, revision or check-in is offered at a time. In the text client a proposal prints once when created. In the voice client it becomes a notice announced through the existing ask-first path, answered with yes (approve), no (reject), or "not now" (kept for later), classified by the existing intent classifier. The question is built in code from the stored topic, not written by the model.

**10. Privacy.** The interests file is owner-only. `/interests why <id>` shows the evidence quotes; `forget <id>` deletes the interest and its evidence; `forget all` clears everything and the run history. Evidence stores a quote of the user's utterance (up to 120 characters), so deleting an interest actually deletes that copy. Turning reflection off does not delete anything.

## Risks / Trade-offs

- [Wrong or creepy inferences] → nothing is used until approved, evidence is shown, rejected topics never return, financial turns are excluded.
- [Nagging] → one proposal at a time, three per run, a daily nudge cap, mute, and a feature switch.
- [Personal text sent to the model provider for reflection] → only the user's own short utterances, no replies or tool output, financial turns excluded, a switch to turn it off, and one call a day at most.
- [Prompt injection via utterances] → the utterances are the user's own words, but they may quote pasted text; the reflection call can only return the forced-schema topics, which then need the user's approval, and it has no tools.
- [The model states a wrong event date] → the nudge note forbids stating dates as fact and routes lookups through the research flow.
- [Word-overlap matching is crude] → acceptable at a few dozen topics; duplicates are caught by the user at approval time.

## Open Questions

- Should reflection default to on? Proposed: on, because nothing is used without approval and the first batch is shown to the user.
- Is 30 days of history the right window? Starting there; configurable.
