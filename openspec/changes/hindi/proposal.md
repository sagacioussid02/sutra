## Why

Sutra will be spoken to in Hindi, and the user wants translation. Language support is mostly the model's job, but four things around it are not: the confirmation path (a "haan" or "nahi" must be understood as safely as "yes" and "no"), the code-matched safety nets (humor, listening mode, crisis), the deterministic reminder parser, and the voice itself (which language is heard and spoken, and how).

## What Changes

- **Safe confirmations in Hindi and Hinglish.** The fast path keeps its rule of "only what can never mean anything else", now with a short list of Hindi and Hinglish words, matched in both scripts. Any reply that mixes scripts or is not on the list goes to the isolated classifier, whose prompt now covers Hindi and Hinglish with examples, and a labelled Hindi set joins the evals. A mixed-script reply can no longer collapse to an English "yes".
- **Replies in the language spoken.** Sutra answers in the language the user used, Hindi in Devanagari so it is spoken properly. The fixed replies on the confirmation and offer paths (declined, expired, "was that a yes or a no?", "I heard...") have Hindi versions.
- **Hindi reminders.** "मुझे 5 मिनट बाद याद दिलाना कि चाय बनानी है", "kal subah 9 baje yaad dilana..." are read by the same deterministic parser and answered in Hindi. An hour with no morning or evening is asked about in Hindi and the answer is understood in Hindi.
- **Translate.** One-off translation works by asking. New: an interpreter mode ("be my interpreter between English and Hindi") in which every message is translated into the other language and nothing else is done: no tools, no unprompted offers, no humor, not remembered as a topic. "Stop interpreting" ends it.
- **Voice.** The text-to-speech style tells the voice to speak Hindi as a native speaker would. The local voice picks a Hindi voice for Devanagari text; local speech recognition can be given a multilingual model and a language.
- **Safety nets in Hindi.** The heavy-topic and upset word lists, listening mode, and crisis wording gain Hindi and Hinglish wording, and humor stays off for Hindi turns until its own tuning exists.

Out of scope: other languages, a full Hindi version of every message (only the confirmation, offer, and reminder paths), Hindi humor, and Hinglish spelling variants beyond the common ones.

## Capabilities

### New Capabilities
- `hindi`: Hindi and Hinglish confirmations, replies, reminders, interpreter mode, and voice settings, with the safety nets extended.

### Modified Capabilities
(none)

## Impact

- New `i18n.py` (language detection and fixed-reply translations) and `translate.py` (interpreter mode detection).
- `classifier.py` normalization keeps Devanagari; the classifier prompt and the eval set grow.
- `reminders/` gets a Hindi front end that rewrites a Hindi request into the form the existing parser reads.
- Voice settings: `SUTRA_LOCAL_VOICE_HI`, `SUTRA_LOCAL_STT_LANGUAGE`.
