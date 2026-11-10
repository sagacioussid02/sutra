#!/usr/bin/env bash
# Starts the Sutra gateway with its secrets loaded from ~/.config/sutra/sutra.env.
# launchd runs this (deploy/launchd/com.sutra.gateway.plist); you can also run
# it by hand to check that everything starts. Config files and the SQLite
# databases stay where they are today: in the gateway/ directory.
set -euo pipefail

REPO_DIR="${SUTRA_REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="${SUTRA_ENV_FILE:-$HOME/.config/sutra/sutra.env}"

# shellcheck source=deploy/lib.sh
. "$REPO_DIR/deploy/lib.sh"
load_env "$ENV_FILE"

cd "$REPO_DIR/gateway"
# Extra flags are word-split on purpose.
# shellcheck disable=SC2086
exec "$REPO_DIR/gateway/bin/gateway" \
  -addr "${SUTRA_GATEWAY_ADDR:-127.0.0.1:8765}" \
  -tokens tokens.yaml \
  -discovery-sources discovery-sources.yaml \
  -events events.yaml \
  ${SUTRA_GATEWAY_EXTRA_FLAGS:-}
