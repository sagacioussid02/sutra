## Why

For testing, the user wants Sutra to start on a button or a wake word, with always-on listening to come later. As it grows more capable, they also want a dependable way to rein it in: turn it off, or limit it to looking things up, by a key or a spoken keyword. Those two belong together: the wake word is only comfortable if the off switch is certain, and "always on" should not be built until it is.

## What Changes

- **Three modes.** `full` (everything), `limited` (answers and looks things up only: gateway tools that only read, no changes, no spending, no unprompted speech, no research runs, no feeds, no group chat), and `off` (not listening and not answering). The mode is saved, so a restart never silently returns to a higher one.
- **Lowering is easy, raising is deliberate.** A key press or a spoken keyword ("safe mode", "limited mode", "go quiet", "stop listening") drops the mode at once, even from a mumbled or low-confidence transcript, and cancels any action awaiting confirmation. Raising it back needs the keyboard (a key in the voice client, or `/mode full`); no spoken phrase can raise it.
- **A silent distress phrase.** If the user sets a private phrase, saying it anywhere in a sentence drops Sutra to `limited` without announcing it: the rest of the sentence is handled normally, but nothing that changes anything can happen. The phrase is never logged or shown.
- **A wake word.** `SUTRA_ACTIVATION=wake` keeps listening on the machine, checks each utterance with local speech recognition, and sends nothing to the cloud until it hears "Hey Sutra" (or a configured phrase). After that, the conversation continues without repeating it, as it does now. The button (Enter) still works at any time. `button` remains the default.
- **Always-on is not built yet.** It would listen and answer without a wake word; it comes after the wake word proves itself, with `limited` as its safe fallback.

Out of scope: the question-and-answer authentication for higher permissions (designed separately), starting automatically at login, and voice-based speaker recognition.

## Capabilities

### New Capabilities
- `activation-safe-mode`: the three modes with reduce-only voice control, the silent distress phrase, and wake-word activation.

### Modified Capabilities
(none)

## Impact

- New package `orchestrator/src/sutra_orchestrator/safety/` and a saved mode file (owner-only).
- `Orchestrator` filters tools by mode, drops a pending action when the mode drops, and stays quiet when not `full`. The offers arbiter, idle research, the feeds and the group chat all check the mode. The voice client gains mode keys, an `off` state, and the wake-word loop.
- New setting `SUTRA_ASSISTANT_GENDER` (default feminine) for first-person Hindi.
