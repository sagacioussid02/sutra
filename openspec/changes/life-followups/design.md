## Context

The pieces exist: episodes close and are summarised, the offers system asks one thing at a time and learns a bar, and the personality rules already know which topics are heavy. This change adds a small store of people and plans, a prompt block, check-ins through the offers system, and a listening mode.

## Decisions

**1. Extraction rides on episode close.** The graph calls a hook with the closed episode's user lines (replies are not read; turns that used excluded tools and low-confidence turns are never in the buffer). A forced-schema call, given today's date, returns people (`name`, `relation`) and plans (`text`, `when` as an ISO date or empty, `who`). Code validates: a name is 2 to 30 letters and spaces; a relation or text is short; a date must parse and fall between yesterday and 400 days ahead; anything matching the heavy-topic words is dropped. People merge by name; plans dedupe by similar words and date. Caps (200 people, 100 upcoming) are rails.

**2. A small prompt block.** Up to ten lines, "Sam (brother)" and "dentist appointment, tomorrow", with people named in the current utterance first, introduced as background that is not an instruction. Names also feed the recognizer hint at startup.

**3. Check-ins are open questions asked directly.** A plan is due the day after its date and expires three days later. The service creates a ready signal of kind `checkin` with a code-built question ("How did the dentist appointment go?"). It skips the judge, as a question to the user is not something to weigh, but it passes the arbiter, so it is one at a time, never during a confirmation, and subject to blocks. A check-in is created only while the `checkin` bar is below 0.8: engaged answers lower it, ignores and declines raise it, deferrals leave it.

**3a. Engaged, not "yes".** The answer to a check-in is not yes or no. A reply counts as engaged unless it is a deferral or a refusal, it is not clearly about something else (it shares a word with the plan or uses an ordinary evaluative word such as good, fine, rough, went), and so on. On engagement the next turn gets a short note: you asked this, they answered, respond with real interest and at most one follow-up question; if they changed the subject, follow them.

**4. A learned wellbeing question.** When the user's message is a greeting and enough days have passed since the last wellbeing question, a ready signal asks "How have you been lately?" The gap is `2 + 15 x (bar - 0.3)` days, so a welcomed question comes back sooner and an ignored one much later.

**5. Listening mode.** Phrases such as "rough day", "need to vent", "just want to talk", "I feel sad/anxious/lonely/overwhelmed" start it for five turns (refreshed by more of the same). A turn in the mode gets a note: do not fix or list; reflect what they said; ask at most one gentle question; no jokes; no advice unless asked; you are not a therapist and should say so only if it matters. While it lasts, no humor is offered, no unprompted offer is appended, and the turns do not enter the graph. A crisis phrase (wanting to die, ending one's life, hurting oneself) adds a second note: respond with warmth first; say you are glad they told you; encourage reaching someone they trust now and a crisis line or emergency services (in the US, 988 and 911); stay with them; give no methods. These phrases are matched in code on the user's own words.

**6. Control and privacy.** `life.db` is owner-only. `/life` shows people and plans; `/life forget person|plan <id>`, `/life forget all`, `/life add plan <date> <text>`. Names go to the recognizer only in cloud mode and only as vocabulary. Conversation memory still records what was said, so `/forget` there remains the way to erase a conversation.

## Risks

- A sensitive plan slips past the heavy-topic words: the words are broad, the user can forget anything, and a check-in is only a question.
- Listening mode triggers on a casual "I feel tired": it only changes tone for a few turns.
- Crisis detection by phrases misses indirect wording and cannot replace a person: the note is a safety net, not a guarantee, and this is said in the README.
