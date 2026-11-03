## Context

Sutra can read, change, spend, speak unprompted, call the web and open a chat with another app. Each of those already has its own control, but there is no single, certain way to say "less". The safest design is one mode that every one of those paths consults, where the voice can only ever lower it.

## Decisions

**1. One mode, three levels, checked in code.** `full`, `limited`, `off`. A single `SafetyService` holds it and is asked, never told. It is saved to an owner-only file; if the file is unreadable the mode is `limited`. The configured starting mode (`SUTRA_START_MODE`, default `full`) applies only when nothing is saved, so the saved mode wins, and a lowered mode survives a restart.

**2. What `limited` allows.** Direct answers, reminders, memory, and gateway tools that only read. A gateway tool counts as reading if the word after its project prefix is get, list, read, show, find, search, describe, view, status or check (`finanxe_list_debts`, `finanxe_get_snapshot`); anything else is blocked, including names the rule has not seen. The gateway's tier is not visible to the orchestrator, so this is a conservative filter on names, and `SUTRA_LIMITED_TOOLS` adds exceptions by name. Local tools that only reduce behaviour (stop offers, mute, retire, humor) stay; the one that spends money (research) does not. A blocked tool is removed from what the model is offered and refused if the model asks anyway.

**3. What `limited` stops.** Anything unprompted: follow-up offers, check-ins, lesson questions, heads-ups, interest suggestions, wellbeing questions (all pass through the offers arbiter, which now refuses); idle research and the feeds (no outgoing requests); the group chat. The confirmation gate is unchanged, and an action already awaiting confirmation is dropped the moment the mode drops, and cannot be confirmed afterwards.

**4. `off`.** The orchestrator answers every message with one line saying it is off and how to turn it back on. The voice client releases the microphone and listens to nothing but the keyboard. Reminders still fire silently into the inbox.

**5. Voice can only lower.** Keywords are matched as a whole short utterance (not inside a longer sentence), in English and Hindi: limited ("safe mode", "limited mode", "read only mode", "सेफ मोड"), off ("go quiet", "mute yourself", "stop listening", "switch off", "चुप हो जाओ"). They work regardless of transcript confidence, because lowering is always safe. Nothing spoken raises the mode; the typed `/mode full|limited|off` and the voice client's keys (`f`, `s`, `m`) do, because they need a person at the keyboard.

**6. The silent distress phrase.** `SUTRA_DURESS_PHRASE`, never shown or logged (the setting hides it from any printout), is matched on normalized text anywhere in an utterance. On a match the mode drops to `limited`, any pending action is dropped, the phrase is cut out of the text, and the rest is handled as an ordinary message in `limited`, with no announcement. If the rest asks for something that changes anything, Sutra says it cannot do that right now, which is also what an observer would expect. Restoring needs the keyboard.

**7. Wake word by local recognition.** In `wake` mode the microphone stays open on this machine. Each spoken segment is transcribed by the local recognizer (never the cloud), and matched against the wake phrases with a little fuzz for how the name tends to be misheard (`sutra`, `sootra`, `suitra`, `shutra`). A match with words after it is handled as the command; a bare match gets "Yes?" and a normal listen. The cloud recognizer is used only after the wake word. If the local recognizer is not installed, the voice client says so and stays on the button. The button (Enter) works at any time in every activation mode. Always-on (no wake word) is deliberately left for later.

**8. Gender in Hindi.** `SUTRA_ASSISTANT_GENDER` (feminine by default, or masculine, or neutral) adds one line to the prompt so first-person Hindi uses the chosen forms. The fixed Hindi replies were already written neutrally.

## Risks

- A tool whose name hides a change (a name like `get_and_delete`): the verb rule looks at the first word only, so such a tool would be allowed. Names in this project follow verb_noun; the override list is the escape hatch, and the gateway's own confirmation gate still applies.
- A false keyword trigger: lowering is cheap to undo at the keyboard, and keywords must be the whole utterance.
- Wake word misses or false wakes: expected from a first version; the button always works, and the README says to expect to tune it.
