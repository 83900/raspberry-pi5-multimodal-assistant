#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
voice_dir="$HOME/.local/share/piper"
mkdir -p "$voice_dir"

"$project_dir/.venv/bin/python" -m piper.download_voices --data-dir "$voice_dir" \
  zh_CN-huayan-medium en_US-lessac-medium

echo "Piper voices installed in $voice_dir"
echo "Confirm PIPER_ZH_VOICE and PIPER_EN_VOICE in ~/.config/pi-edge-assistant/edge-assistant.env"
