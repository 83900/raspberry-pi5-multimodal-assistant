#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_dir="$HOME/.config/pi-edge-assistant"
data_dir="$HOME/.local/share/pi-edge-assistant"
service_dir="$HOME/.config/systemd/user"

if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "Warning: this installer is intended for 64-bit Raspberry Pi OS (aarch64)." >&2
fi

sudo apt update
sudo apt install -y python3-venv python3-dev build-essential cmake git curl ffmpeg alsa-utils rpicam-apps python3-picamera2

python3 -m venv --system-site-packages "$project_dir/.venv"
"$project_dir/.venv/bin/python" -m pip install --upgrade pip
"$project_dir/.venv/bin/pip" install "$project_dir[pi]"

mkdir -p "$config_dir" "$data_dir" "$service_dir"
if [[ ! -f "$config_dir/edge-assistant.env" ]]; then
  sed "s|%h|$HOME|g; s|/run/user/1000|/run/user/$(id -u)|g" \
    "$project_dir/deploy/edge-assistant.env.example" >"$config_dir/edge-assistant.env"
  chmod 600 "$config_dir/edge-assistant.env"
fi

sed "s|@PROJECT_DIR@|$project_dir|g" "$project_dir/deploy/pi-edge-assistant.service.in" \
  >"$service_dir/pi-edge-assistant.service"
sed "s|@PROJECT_DIR@|$project_dir|g" "$project_dir/deploy/pi-edge-wakeword.service.in" \
  >"$service_dir/pi-edge-wakeword.service"

systemctl --user daemon-reload
systemctl --user enable pi-edge-assistant.service
sudo loginctl enable-linger "$USER"

echo "Installed. Next:"
echo "  1. Run scripts/setup_whisper.sh"
echo "  2. Run scripts/setup_models.sh --compare"
echo "  3. Configure Piper voices and ALSA devices in $config_dir/edge-assistant.env"
echo "  4. Start with: systemctl --user start pi-edge-assistant"
echo "  5. Read token with: cat $data_dir/access-token"
echo "  6. Configure WAKEWORD_COMMAND, then optionally enable pi-edge-wakeword.service"
