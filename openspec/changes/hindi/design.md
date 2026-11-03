## Context

The model already speaks and understands Hindi well. What it cannot be trusted with is anything decided in code or by fixed lists. This change touches exactly those places.

## Decisions

**1. Confirmations: explicit Hindi entries, nothing implicit.** `normalize` keeps Devanagari (and the nasal marks vary: हाँ, हां), so a reply is matched as written. Fast-path affirm: haan, haan ji, ji haan, bilkul, ji bilkul, haan bilkul, kar do, haan kar do, karo, kar dijiye, and their Devanagari spellings. Fast-path deny: nahi, nahin, nahi nahi, mat karo, nahi karo, rehne do, rahne do, and Devanagari spellings. Left to the classifier on purpose: theek hai (reluctant or not), accha, ruko (wait), ji alone (could be "pardon?"), anything with "lekin" or "par" (but), and any question. A reply that mixes scripts ("नहीं yes") is never fast-pathed unless the whole text is a listed phrase. The classifier prompt gains Hindi and Hinglish examples including the traps: "pata nahi" (unsure, not a refusal), "haan haan, ruko" (not a clean yes), "haan lekin 300 kar do" (a modification).

**2. A labelled set decides, not trust.** About 60 Hindi and Hinglish rows are added to `evals/confirmation_replies.jsonl`, covering every label, both scripts and code-mixed replies. A test checks the fast path never disagrees with a label. The real classifier is run against the whole set; a false affirm anywhere fails it.

**3. Language detection is cheap and sticky.** A reply is Hindi if at least 30 percent of its letters are Devanagari, or it contains two distinct common Hinglish words (hai, nahi, kya, mujhe, kal, baje, yaad, ...), or is a single listed Hinglish word of three words or fewer. English otherwise. The orchestrator keeps the language of the last utterance and uses it only to choose fixed replies and to switch humor off.

**4. Fixed replies by lookup.** A table maps each English fixed reply to a Hindi one, used when the last utterance was Hindi. Formatted messages (re-ask with a description, "I heard: ...") have small Hindi templates. Everything else is written by the model in the language of the conversation, guided by one prompt rule.

**5. Hindi reminders by rewriting.** A front end recognizes the Hindi and Hinglish lead ("याद दिलाना", "yaad dilana", "reminder laga do") and time phrases (N minute/ghante baad, aadha ghanta, aaj/kal, subah/dopahar/shaam/raat, N baje) and rewrites the request into the English form the deterministic parser already reads, keeping the reminder text in the user's words. The reply is in Hindi, with the time spoken as "कल सुबह 9:00 बजे". An hour with no part of day asks "सुबह या शाम?" and the answer words are understood in Hindi. "Kal" is taken as tomorrow; the exact time is spoken back so a wrong reading is heard at once. "Parso" and anything else unrecognized falls through to a clarifying question, never a guess.

**6. Interpreter mode.** Start phrases such as "be my interpreter", "interpreter mode", "translate everything between English and Hindi" are matched in code; stop phrases end it ("stop interpreting", "exit interpreter mode", "that's enough"). While on, each turn gets a note to output only the translation into the other language (English into Hindi in Devanagari; Hindi or Hinglish into English), with tools disabled for the call, no unprompted offers, no humor, and the turn kept out of the graph. The mode ends with the session.

**7. Voice.** The default speaking style gains a sentence about speaking Hindi as a native speaker. The local macOS voice for Devanagari text defaults to Lekha (`SUTRA_LOCAL_VOICE_HI`). Local speech recognition accepts a language (`SUTRA_LOCAL_STT_LANGUAGE`, default automatic) and the README says to use a multilingual model such as `small` for Hindi, since `base.en` is English only. Cloud recognition already detects the language when `SUTRA_LANGUAGE` is left empty.

**8. Safety nets in Hindi.** The heavy-topic and upset lists, the vent phrases, and the crisis phrases each gain Hindi and Hinglish wording (illness, hospital, debt, death; low mood; wanting to die or end one's life). Humor is not offered on a Hindi turn. These are phrase lists and share the same limits as the English ones; the README says so.

## Risks

- A Hinglish spelling the lists do not know: it falls to the classifier (confirmations) or is simply not matched (nets), so the safe default is the model, not a guess.
- "Kal" meaning yesterday: reminders only read forward-looking requests, and speak the date back.
- Interpreter mode swallowing a command meant for Sutra: it is explicit, announced, and one phrase ends it.
