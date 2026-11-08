## Context

`text-orchestrator` built the seam this change stands on: a turn
function that takes one utterance as text and returns one reply as
text, with confirm-first actions gated by the confirmation classifier
rather than by the conversational model. The REPL (`repl.py`) is,
in its own words, "a thin loop over `Orchestrator.respond`" — proof
the pipeline already separates *what a turn does* from *how it is
presented*. Voice then wrapped the same pipeline in STT and TTS, with
its own presentation machinery (the sentence splitter in
`streaming.py`, fillers, interruption handling).

What is missing is a presentation built for a person testing the
system at a screen: persistent, scrollable, honest about state. The
REPL shows the reply and nothing else; the decisions a tester most
needs to see — classifications, deferrals, staleness — scroll away in
log lines, if they appear at all. Meanwhile the rest of the system
keeps growing surfaces that assume such a place exists: world-state's
manual checks, the arbiter's deferred offers, principal state
editing. They are all operable from the REPL's slash commands, and
all of them are miserable there.

## Goals / Non-Goals

**Goals:**
- Chat and voice are the same assistant: identical turn processing,
  memory, tools, confirmation flow, and arbiter, differing only in
  transport.
- The surface makes the pipeline's decisions observable enough to
  test — visibly, in the transcript, not only in logs.
- A session survives restarts and can be reviewed: what was asked,
  what was done, what is pending.
- Zero new exposure: local-first, authenticated, no new network
  surface beyond the owner's own machines.

**Non-Goals:**
- A chat product. No multi-user support, no sharing, no public
  deployment, no polish budget beyond clarity.
- A different assistant. No chat-specific prompt, tools, memory, or
  safety behaviour. Anything chat needs from the pipeline, voice
  gets too, because it is the pipeline.
- Voice behaviours in text. No fillers, no speakable-sentence
  splitting, no interruption or barge-in handling; and no
  text-only behaviours that would change outcomes (no edit-and-resend
  of a consumed turn, no retry button that replays a turn).
- Replacing the REPL. It stays the developer's loop; chat is the
  resident's surface.

## Decisions

### The turn handler is shared; surfaces consume its events
The one refactor this change allows itself: `Orchestrator`'s turn
processing is factored so a turn yields a stream of events — text
deltas as the model produces them, tool-call started and finished
(with the tool and its outcome), confirmation pending, offer created
or deferred, turn completed or failed — and each surface consumes
the events in its own way. `respond()` becomes the assembling
consumer the REPL already treats it as; the voice client keeps
consuming text through its sentence splitter; chat renders events as
they arrive.

*Why:* without a shared event stream, chat would have to reconstruct
state from the final reply text — guessing which pause was a tool,
which question was a confirmation — and every guess is a place the
test surface can lie about the system it is testing. Events from the
pipeline are the pipeline's own account of itself.

*Alternative considered:* chat as a websocket wrapper around the
REPL, parsing its output. Rejected: the REPL's output is a rendering
for humans at a terminal, and parsing a rendering to rebuild state
inverts the dependency this repo has kept clean since
`text-orchestrator`.

*Constraint:* the refactor must not change voice behaviour. The
voice client's consumption — sentence by sentence, with its existing
lead-in rules — is the regression suite's first citizen, and the
existing tests pin it before the chat work begins.

### Served by the orchestrator, static UI, no build step
The chat server is a small component of the orchestrator process
(new `chat` package), not a gateway feature: the gateway is the tool
layer and never sees conversation. The server exposes a turn
endpoint and a server-sent-events stream of the turn's events, and
serves the UI as static files bundled in the package — one page, no
framework, no build step, no external requests. It binds localhost
by default; binding a tailnet interface is explicit configuration.

*Why:* the orchestrator already holds everything the surface needs —
the pipeline, the session, the stores. A separate web tier would
need its own channel back into the session and would duplicate the
identity question this change is trying to inherit, not re-ask.

### Confirmations are typed, classified, and never buttons
A pending confirmation renders as a distinct transcript state
showing what is being confirmed. The user answers by typing; the
reply is routed to the pending confirmation and classified by
`classifier.py`, exactly as a spoken reply is — the same isolation
(the classifier sees the pending description and the reply, not the
conversation), the same conservative bias, the same eval set applies
unchanged. The UI renders no approve or deny button, and no keyboard
shortcut that synthesises an answer.

*Why:* in Muse's chat, buttons are chrome. Here, the classified
reply *is* the security mechanism for confirm-first actions; a
one-click confirm would be a second, weaker gate beside it, and the
test surface would stop exercising the gate that voice depends on.
What is being dogfooded is the classifier's judgement over words, so
words are what the surface must collect.

### The transcript is a surface record, not a memory
The transcript store keeps the session as rendered: user turns,
replies, tool actions with outcomes, confirmation states, and — in
debug mode — decision annotations. It is per user, local,
schema-versioned, and clearable by its owner. It is *not* an input
to the assistant's memory: recall and recording continue to run
through the pipeline's own memory interface, exactly as in voice, so
a long chat transcript cannot quietly become a second memory store
with different rules. Reviewing the transcript is for the user; the
assistant does not read it back as context beyond the live session's
own history handling, which is unchanged.

### Debug is a view over real decisions
The debug toggle annotates turns with decisions the pipeline
actually made, read from the turn events and the owning stores: a
turn consumed as a confirmation reply, with the classifier's label;
an offer deferred, with the arbiter's recorded reason (over budget,
over cap, quiet hours); a snapshot field rendered stale. Annotations
are generated from the same records the control commands show
(`/state`, `/inbox`), so debug cannot drift into a parallel account.
The toggle is per-session, defaults off, and is a pure view: the
spec pins that outcomes with the toggle on are identical to outcomes
with it off.

*Why:* the toggle exists because the failure mode of a test surface
is a plausible story. Annotations sourced from the stores are the
system testifying about itself; annotations inferred by the UI would
be the UI testifying about its guesses.

### Identity: the owner's token now, the mapping when it lands
The chat server requires the bearer token the orchestrator already
authenticates with, and until `per-user-identity` lands it serves
the single owner's session — an assumption stated in the README, not
buried. The turn endpoint resolves its user through one named hook;
when `per-user-identity` lands, that hook adopts its token-to-user
mapping and the transcript store's per-user keying, already in place,
starts meaning more than one person. No data migration is needed at
that point because transcripts were per-user from the first commit.

### Failure: actions fail closed, the surface degrades honestly
If the stream drops mid-turn or the server fails, the turn is marked
failed in the transcript and no confirm-first action may complete
from that turn — a confirmation that was pending stays pending, and
answering it requires a new, complete turn. Read-only content that
already arrived may remain visible, labelled partial. If the gateway
is unreachable, chat says so; it never renders a fabricated reply to
fill the silence. A dead chat server changes nothing about voice or
the REPL, which share the pipeline but not the surface.

## Risks / Trade-offs

- [The event refactor disturbs voice] → existing voice-path tests
  pin behaviour before the refactor; `respond()`'s contract (one
  utterance in, one reply out) is preserved for its current callers;
  the refactor lands as its own task, before any chat code.
- [Chat becomes the "real" interface and voice rots] → the manual
  checks and this change's own test script run the *same* scripted
  session through chat and the REPL, and the dogfooding guidance is
  explicit: chat is where testing happens, voice is what is being
  built. Parity is a spec requirement, not a hope.
- [Debug annotations leak into normal use] → off by default,
  per-session, and rendered as annotations on the surface only; the
  transcript's non-debug view is what persists as the plain record.
- [A web surface is an attack surface] → localhost by default, token
  required, no external assets to supply-chain, and the surface can
  do nothing the REPL cannot — it holds no authority of its own; the
  pipeline's gates are the only gates.
- [Transcript grows without bound] → it is the owner's record to
  clear, with a control command; growth is a disk line item on the
  owner's machine, not a correctness risk, and retention policy is
  deliberately the owner's call.

## Migration Plan

The event-stream refactor lands first and alone, verified against
the existing suite; the REPL and voice client move onto it without
visible change. The chat server ships behind `SUTRA_CHAT` (off by
default), then the UI, then the debug toggle. Disabling the switch
leaves the system exactly as it was, minus a dormant package.

## Open Questions

- Should chat eventually relax the speakable-output prompt (tables,
  longer structured answers) now that a screen can render them?
  Design says not in this change: a relaxed prompt makes chat a
  different system from voice, and the surface's whole value is that
  it is not. Revisit only if dogfooding shows the constraint, not
  the transport, is what makes chat feel limited.
- Server-sent events versus a websocket: SSE is chosen for a
  one-way event stream with a POST per turn — simpler, and nothing
  in the surface needs server push outside a turn. Revisit if
  proactive delivery to an open chat window is ever wanted; that
  would be its own change, and acknowledgments and offers already
  have their delivery rules.
