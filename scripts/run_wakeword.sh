#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${WAKEWORD_COMMAND:-}" ]]; then
  echo "WAKEWORD_COMMAND is not configured" >&2
  exit 2
fi

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$project_dir/.venv/bin/python" "$project_dir/scripts/wakeword_bridge.py" \
  --command "$WAKEWORD_COMMAND" \
  --record-seconds "${WAKEWORD_RECORD_SECONDS:-8}" \
  --token-file "${EDGE_DATA_DIR:-$HOME/.local/share/pi-edge-assistant}/access-token" \
  --url "http://127.0.0.1:${EDGE_PORT:-8080}"
