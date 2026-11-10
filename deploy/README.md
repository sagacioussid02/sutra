# Running Sutra all the time (macOS)

Two launchd agents keep Sutra up without a terminal open:

| Agent | What it does |
|---|---|
| `com.sutra.gateway` | Runs the gateway on 127.0.0.1:8765. Starts at login, restarts if it exits. Logs: `~/Library/Logs/sutra/gateway.log`. |
| `com.sutra.watch` | Every 5 minutes, checks each service's health route and sends an ntfy push when one goes down (after 2 failed checks in a row), turns degraded, or comes back. Logs: `~/Library/Logs/sutra/watch.log`. |

Both read secrets from `~/.config/sutra/sutra.env`, which must be `chmod 600`. Nothing secret lives in the repo.

## Install

```bash
deploy/install-macos.sh          # first run creates ~/.config/sutra/sutra.env and watch.yaml
$EDITOR ~/.config/sutra/sutra.env  # FINANXE_API_TOKEN, SUTRA_WATCH_NTFY_TOPIC
deploy/install-macos.sh          # second run builds, loads both agents, checks /healthz
deploy/run-watch.sh -test-notify # one test push to your phone
```

`gateway/tokens.yaml` (and `discovery-sources.yaml` / `events.yaml`, if you use them) stay in `gateway/` as today, and so do the SQLite databases.

Re-run `deploy/install-macos.sh` after pulling changes: it rebuilds and reloads. `deploy/install-macos.sh --uninstall` removes the agents and leaves config and logs alone.

## Health

- Gateway: `GET http://127.0.0.1:8765/healthz` (no auth) returns `{"status":"ok","tools":N}`.
- Each project's own route goes in `~/.config/sutra/watch.yaml`. A JSON body with `"status": "degraded"` is reported as degraded; any non-2xx, timeout or refused connection counts as down.
- `deploy/run-watch.sh -dry-run` prints the current state of every target without sending anything.

## Project tokens

A project that protects its API with a header gets it through `discovery-sources.yaml` (`auth_header` + `auth_env`, see `gateway/discovery-sources.example.yaml`) and the value through `sutra.env`. finanxe's hand-written adapter reads `FINANXE_API_TOKEN` directly (`-finanxe-token-env` to change the name). Use the same value finanxe itself uses: its `FINANXE_API_TOKEN`, or the contents of `finanxe/poc/backend/.finanxe_api_token`.

## Limits

launchd agents run only while you're logged in and pause while the Mac sleeps. That's fine while Sutra's clients run on the same Mac; an always-on box is a later step.
