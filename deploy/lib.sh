# shellcheck shell=bash
# Shared helpers for the deploy scripts. Sourced, not run.

# load_env FILE: export every KEY=value in FILE, refusing a file that other
# users can read (it holds API tokens).
load_env() {
  local file="$1"
  if [ ! -f "$file" ]; then
    echo "sutra: $file not found; starting without it (copy deploy/sutra.env.example)" >&2
    return 0
  fi
  local mode
  if [ "$(uname)" = "Darwin" ]; then
    mode="$(stat -f '%Lp' "$file")"
  else
    mode="$(stat -c '%a' "$file")"
  fi
  case "$mode" in
    600|400) ;;
    *) echo "sutra: refusing $file: permissions are $mode, want 600 (chmod 600 $file)" >&2; exit 1 ;;
  esac
  set -a
  # shellcheck disable=SC1090
  . "$file"
  set +a
}
