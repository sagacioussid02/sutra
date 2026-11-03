## Context

The user wants Sutra to feel less like a robot, and said humor is hard because it is personal: start with some, then adjust the values. The design is a small learning loop around a few dials, with safety rules the model cannot override.

## Decisions

**1. Dials, not a switch.** `level` 0 to 10 sets the chance that an eligible turn offers humor (level divided by 24, so level 3 is one turn in eight) and sets the minimum gap in turns between offers (24 divided by level, at least 3). `variety` 0.2 to 2.0 (default 0.7) is a softmax temperature over style scores: low sticks to what has worked, high keeps trying others. These are two different things from the model's sampling temperature, which this change does not touch.

**2. Five styles, each a one-line instruction.** `dry` (deadpan understatement), `self` (gentle humor about being an AI or its own limits, never about the user), `tease` (light, affectionate, about something the user said in this conversation, nothing sensitive), `wordplay` (a light pun on the topic), `absurd` (a playful exaggerated comparison). Scores start at 0.5, `tease` at 0.3, and stay within 0.05 to 0.95.

**3. Eligibility is code.** A turn is eligible only if humor is on and the level is above zero; no tool has been used in the turn so far; no action is awaiting confirmation and the turn carries no other instruction note; the transcript is not flagged doubtful; the user's words contain no heavy-topic words (money and debt, illness and health, death and loss, family trouble, legal trouble, crisis) and no sign of frustration or upset, and none did on the previous three turns; and the minimum gap has passed. Then a random draw at the level's chance decides. The note is added only to the first model call of the turn: after any tool call the later calls do not carry it, and the confirmation read-back never does. Alternative: tell the model in the prompt when not to joke. Rejected: the model cannot be relied on for that, and the rules need to be testable.

**4. The note.** When a turn is picked, one style is chosen by softmax over the scores and the note says: "If it fits naturally, you may add one short light touch of humor in this style: <instruction>. One line at most. If nothing natural comes to mind, say nothing funny. Never joke about money, health, family, loss, or anything the user seems upset about."

**5. Learning from the reaction.** Whether a joke was actually made is not known until the model answers, so the next turn starts a background check: one small structured call sees Sutra's last reply and what the user said next and returns `joked` (boolean), `reaction` (`laughed`, `smiled`, `neutral`, `groaned`, `annoyed`) and `stop` (the user asked for no more jokes). Only when `joked` is true: the style score moves by +0.12, +0.05, -0.02, -0.10 or -0.20 for the five reactions. After ten judged jokes the level moves one step up if at least six were laughed or smiled at, and one step down if at least four were groaned or annoyed, never above 6 by itself (the user can set it higher). `stop` sets the level to 0. The check runs beside the next turn and adds no waiting. If it fails, nothing changes.

**6. Control.** A local tool `adjust_humor(change)` with `more`, `less`, `off` or `on` lets the model act on "be funnier", "fewer jokes" or "no jokes", moving the level by one step (or to 0 or back to the last non-zero level). `/humor` shows level, variety, style scores and counts; `/humor level N`, `/humor variety X`, `/humor style <name> <score>`, `/humor off|on`, `/humor reset`. The profile is stored in an owner-only database; it holds numbers and counts, no text.

**7. Voice.** The note can name the delivery ("say it flat") but this change does not alter text-to-speech. Humor in Hindi is for the Hindi change.

## Risks

- A joke at a bad moment: the eligibility rules are conservative and keyword-based, so some sensitive moments will slip through; the gap, the low default and the learning loop limit the cost, and one "stop" ends it.
- Learning from a noisy reaction read: bounded steps and a ten-joke window keep one misread from mattering.
- Cost: one small call only after a turn where humor was offered (about one in eight eligible turns at the default).
