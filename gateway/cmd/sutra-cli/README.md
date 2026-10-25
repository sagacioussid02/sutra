# sutra-cli

A text client for the Sutra gateway. This is the Phase 1 milestone: it
proves auth, tiered tool dispatch, the confirm-first flow, and audit
logging all work end to end, on a keyboard, before any voice work starts.

## Setup

1. Have a gateway running (see the top-level README) with a `tokens.yaml`
   defining your user and their `allowed_tools`.
2. Get your bearer token from that `tokens.yaml`.
3. Run the CLI:

   ```sh
   go run ./cmd/sutra-cli -addr http://127.0.0.1:8765 -token <your-token>
   ```

   Or set `SUTRA_TOKEN` instead of passing `-token` every time:

   ```sh
   export SUTRA_TOKEN=<your-token>
   go run ./cmd/sutra-cli
   ```

An invalid or missing token fails immediately with an authentication error
— you never reach the interactive loop.

## Using it

On connect, the CLI lists every tool your token is allowed to call. Then,
repeatedly:

```
tool (blank to quit)> <tool name>
args as JSON (e.g. {} or {"key":"value"})> <arguments>
```

- A **read-only** tool call prints its result immediately — no confirmation
  step.
- A **confirm-first** tool call prints a pending description and an expiry
  time, then asks `confirm? [y/N]>`. Anything other than `y`/`yes` cancels
  — the underlying project is never touched. Typing `y`/`yes` calls the
  gateway's `confirm()` operation and prints the executed result.

Press Enter on a blank tool name (or Ctrl-D) to quit.

## Walkthrough

With a gateway running, twin and finanxe both reachable, and your token
allowed to call `twin_chat`, `finanxe_get_snapshot`, and
`finanxe_set_debt_funding`:

1. **Twin chat** (read-only, executes immediately):

   ```
   tool (blank to quit)> twin_chat
   args as JSON (e.g. {} or {"key":"value"})> {"twin_id": "<a real twin id>", "message": "hi"}
   ```

   You should see `result: {"response":"...","session_id":"..."}`.

2. **finanxe snapshot** (read-only, executes immediately):

   ```
   tool (blank to quit)> finanxe_get_snapshot
   args as JSON (e.g. {} or {"key":"value"})> {}
   ```

   You should see your current financial snapshot.

3. **finanxe mutation, held for confirmation** (confirm-first):

   ```
   tool (blank to quit)> finanxe_set_debt_funding
   args as JSON (e.g. {} or {"key":"value"})> {"debt_name": "<a real debt name>", "account_text": "<an account>"}
   ```

   You'll see `pending confirmation: Redirect funding for debt "..." to
   account "...".` and an expiry time. Type `y` to confirm — you should
   then see `confirmed — result: {"set":true,...}`.

After completing all three, check the gateway's audit log (`sutra-audit.db`,
queryable via `audit.Store.Find`) — you should see all three calls, with
the mutating one appearing twice (once `pending`, once `executed`, both
sharing the same `pending_id`).
