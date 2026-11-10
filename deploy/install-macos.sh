#!/usr/bin/env bash
# Installs the Sutra gateway and sutra-watch as launchd agents on this Mac.
# Safe to re-run: it rebuilds the binaries and reloads both agents.
#
#   deploy/install-macos.sh            build, install, load
#   deploy/install-macos.sh --uninstall  unload and remove the agents (keeps config)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONF_DIR="$HOME/.config/sutra"
LOG_DIR="$HOME/Library/Logs/sutra"
AGENTS="$HOME/Library/LaunchAgents"
LABELS=(com.sutra.gateway com.sutra.watch)
UID_NUM="$(id -u)"

unload() {
  for label in "${LABELS[@]}"; do
    launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  done
}

if [ "${1:-}" = "--uninstall" ]; then
  unload
  for label in "${LABELS[@]}"; do rm -f "$AGENTS/$label.plist"; done
  echo "Removed the launchd agents. Config in $CONF_DIR and logs in $LOG_DIR are untouched."
  exit 0
fi

command -v go >/dev/null || { echo "Go is required (brew install go)" >&2; exit 1; }

echo "Building gateway and sutra-watch..."
(cd "$REPO_DIR/gateway" && go build -o bin/gateway ./cmd/gateway && go build -o bin/sutra-watch ./cmd/sutra-watch)

mkdir -p "$CONF_DIR" "$LOG_DIR" "$AGENTS"
chmod 700 "$CONF_DIR"
if [ ! -f "$CONF_DIR/sutra.env" ]; then
  install -m 600 "$REPO_DIR/deploy/sutra.env.example" "$CONF_DIR/sutra.env"
  echo "Created $CONF_DIR/sutra.env: fill in FINANXE_API_TOKEN and SUTRA_WATCH_NTFY_TOPIC, then re-run this script."
fi
if [ ! -f "$CONF_DIR/watch.yaml" ]; then
  install -m 600 "$REPO_DIR/gateway/watch.example.yaml" "$CONF_DIR/watch.yaml"
  echo "Created $CONF_DIR/watch.yaml with the default targets."
fi
[ -f "$REPO_DIR/gateway/tokens.yaml" ] || { echo "gateway/tokens.yaml is missing (copy tokens.example.yaml)" >&2; exit 1; }

unload
for label in "${LABELS[@]}"; do
  sed -e "s#__REPO_DIR__#$REPO_DIR#g" -e "s#__LOG_DIR__#$LOG_DIR#g" \
    "$REPO_DIR/deploy/launchd/$label.plist" > "$AGENTS/$label.plist"
  plutil -lint "$AGENTS/$label.plist" >/dev/null
  launchctl bootstrap "gui/$UID_NUM" "$AGENTS/$label.plist"
done

sleep 2
if curl -fsS "http://${SUTRA_GATEWAY_ADDR:-127.0.0.1:8765}/healthz"; then
  echo
  echo "Gateway is up. Logs: $LOG_DIR"
else
  echo "Gateway did not answer yet; check $LOG_DIR/gateway.log" >&2
fi
echo "Send a test alert with: $REPO_DIR/deploy/run-watch.sh -test-notify"
