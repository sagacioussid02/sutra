#!/usr/bin/env bash
# One health-check pass over every service in ~/.config/sutra/watch.yaml.
# launchd runs this every 5 minutes (deploy/launchd/com.sutra.watch.plist).
set -euo pipefail

REPO_DIR="${SUTRA_REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="${SUTRA_ENV_FILE:-$HOME/.config/sutra/sutra.env}"

# shellcheck source=deploy/lib.sh
. "$REPO_DIR/deploy/lib.sh"
load_env "$ENV_FILE"

exec "$REPO_DIR/gateway/bin/sutra-watch" \
  -config "${SUTRA_WATCH_CONFIG:-$HOME/.config/sutra/watch.yaml}" "$@"
