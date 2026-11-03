## Context

The gossip app is a local Python server: `POST /api/message {"text"}` returns `{"events": [{"speaker", "kind", "text"}...], "state", "reward"}`; `POST /api/reset`; `GET /api/state`. Its personas speak in brief casual lines, and an "Info Agent" may fetch public facts (it queries public sites for terms in the message). It is not an LLM assistant and has no notion of Sutra's user.

## Decisions

**1. A mode, entered and left by phrase, like interpreter mode.** Start phrases ("catch up with the group", "talk to the group", "hang out with Priya", "open the group chat", "gossip time") and stop phrases ("leave the group", "back to Sutra", "exit hangout", "bye everyone") are matched in code. It cannot start during a held action or an interpreter session (starting one ends the other), and it ends with the session.

**2. The user's words go through untouched.** While in the mode, each message is sent as spoken. No model call composes, summarizes or rewrites it, and the model has no tool that reaches the group. This is the privacy design: the group sees only what the user chose to say to it.

**3. Some things are never forwarded.** A message that matches the heavy-topic or upset words (money, illness, loss, family or legal trouble, in English or Hindi) is not sent; Sutra says it will keep that out of the group. A vent or crisis phrase ends the mode and the turn is handled by Sutra's listening mode.

**4. Said plainly on entry.** One spoken line on entering: the group are fictional friends in a separate app, messages go to that app, and its info bot may look up public facts online. Every persona line is shown with the speaker's name.

**5. Voices.** The speaker takes an optional voice. Defaults: Priya "nova", Rahul "onyx", Ananya "sage", the info bot "echo"; `SUTRA_HANGOUT_VOICES` overrides ("Priya=shimmer,Rahul=ash"). The voice loop speaks each persona's line in its voice, with speak-over working per line. A speaker without voices (the local macOS one) says "Priya says: ...". Short cached phrases include the voice in their key.

**6. Kept apart.** A hangout turn skips the conversation history, the memory record, the graph, and the offers/humor/people paths. The group's lines are never put in the model's context. When the user leaves, Sutra remembers nothing of the conversation beyond the fact that it happened in the session (not even that).

**7. A failure is plain.** If the app does not answer, Sutra says so in one line and stays out of the mode. A bad reply is shown as nothing, not as an error.

**8. A seam.** `GroupClient` is a small interface (`say`, `reset`, `ping`); the implementation uses the standard library against the configured local address. It can be replaced with a client that calls gateway tools without touching the mode.

## Risks

- The info bot sends terms in the user's message to public sites: said on entry, and sensitive topics are not forwarded.
- A real person's name typed into the group stays in that app's own state; Sutra does not copy it.
- Mistaking fiction for fact: names on every line, a spoken label on entry, and nothing stored on Sutra's side.
