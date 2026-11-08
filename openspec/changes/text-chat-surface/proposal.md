## Why

The conversation pipeline is proven in text and wrapped in voice, but
the only text surface is the terminal REPL: a developer's loop over
`Orchestrator.respond`. It is a poor way to live with Sutra. There is
no persisted transcript to scroll back through, no visible difference
between "the model is thinking", "a tool is running", and "a
confirmation is waiting on you", and no way to see *why* something
happened — why a reply was consumed as a confirmation, why an offer
was deferred. So dogfooding means speaking to the voice client, with
all its friction, or typing into a terminal and squinting. The manual
checks in nearly every other change ("start a session, set a presence
hint, create a reminder, confirm the reply reflects it") are all
written as if a comfortable text surface existed. It doesn't.

This change builds one: a chat, in the shape of Muse's — typed turns,
streaming replies, visible machinery — running the *same* pipeline as
voice. Its first job is not to be a product. Its first job is to be
the dogfooding harness: the place Sutra is exercised daily, where its
decisions are observable enough to test, without anyone having to
talk out loud.

## What Changes

- **One pipeline, a third surface.** A local web chat served by the
  orchestrator, beside the REPL and the voice client. A typed turn
  enters the same turn processing as a spoken one — same memory
  recall and recording, same tools through the gateway, same
  confirmation flow, same offers arbiter — and only the transport
  differs. There is no chat-specific reasoning anywhere.
- **Streaming, visible states.** Replies stream as the model produces
  them. Tool calls, pending confirmations, and actions taken render
  as distinct, inspectable states in the transcript rather than
  invisible pauses, so a session can be reviewed afterwards: what was
  asked, what the assistant did, what it is waiting on.
- **Confirmations are answered in words.** A pending confirmation
  shows as its own state; the user's typed reply is consumed by the
  existing confirmation classifier (`classifier.py`), exactly as a
  spoken reply is. The surface deliberately offers no
  click-to-approve control: the classifier over the user's own words
  is the safety mechanism, and a button would be a way around it.
- **A persisted transcript, per user.** The conversation — user
  turns, replies, tool actions with their outcomes, confirmation
  states — is stored per user and survives restarts, so testing can
  resume where it left off and past behaviour can be audited. The
  transcript is a record of the surface, not a new memory: what the
  assistant remembers continues to be decided by the pipeline's own
  memory recording, unchanged.
- **A debug toggle for testing.** An explicit inspect mode, off by
  default, that annotates the transcript with the pipeline's
  decisions: whether a turn was consumed as a confirmation reply and
  how it was classified, offers created or deferred and the stated
  reason, snapshot fields and their staleness. The toggle changes
  only what is displayed, never what is decided.
- **The control commands come along.** Slash commands behave in chat
  as they do in the REPL — the same command handlers (`/remind`,
  `/reminders`, `/inbox`, `/state`, the memory and offers commands) —
  because chat is a surface on the same session, not a new one.
- **Local-first, owner-only.** The server binds localhost by default
  (a tailnet bind is configuration, never a default), and requires
  the same bearer-token authentication the orchestrator already uses.
  Until `per-user-identity` lands, the surface assumes the single
  owner, and says so plainly in its docs.
- Explicit non-goals: no separate "chat brain" or chat-specific
  prompt; no behaviour differences from voice beyond transport (no
  voice behaviours either — no fillers, no sentence-splitting for
  speech, no interruption handling); no multi-user or public chat
  product; no relaxing of the speakable-output prompt for chat in
  this change, because a differently-prompted chat would stop
  measuring the system the voice client actually runs.

## Capabilities

### New Capabilities
- `text-chat-surface`: a local, authenticated web chat that runs
  typed turns through the same conversation pipeline as voice, with
  streaming replies, visible tool and confirmation states, a
  persisted per-user transcript, and an opt-in debug view of pipeline
  decisions

### Modified Capabilities
(none — the pipeline, the confirmation classifier, and the offers
arbiter are consumed as they are; if the shared turn handler needs
refactoring to expose its events, that refactor must not change any
existing requirement of `text-orchestrator`)

## Impact

- Orchestrator: a new `chat` package (server, transcript store,
  event rendering) following the layout of the other feature
  packages; the one structural change is factoring `Orchestrator`'s
  turn processing so the REPL, the voice client, and chat consume
  the same turn handler and its events.
- The chat UI is static files bundled with the package and served by
  the chat server: no build step, no external assets, nothing fetched
  from a CDN — it works on a tailnet-only machine with no internet.
- Storage: a per-user transcript store with the usual protections
  (local SQLite, schema-versioned, 0600). No gateway changes; the
  gateway continues to see only the orchestrator as its client.
- New `SUTRA_CHAT*` settings (enable, bind, port, debug default),
  documented in `orchestrator/.env.example`.
- Depends on `per-user-identity` only for multi-user use, which is
  out of scope: until it lands, the surface runs under the stated
  single-owner assumption and adopts its token-to-user mapping when
  it arrives, at the hook point this change names.
