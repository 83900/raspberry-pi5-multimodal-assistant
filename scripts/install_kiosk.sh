#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
autostart_dir="$HOME/.config/autostart"
desktop_file="$autostart_dir/pi-edge-kiosk.desktop"

if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "Warning: this installer is intended for 64-bit Raspberry Pi OS on a Raspberry Pi." >&2
fi

echo "Display information:"
if command -v wlr-randr >/dev/null 2>&1; then
  display_info="$(wlr-randr 2>&1 || true)"
elif command -v xrandr >/dev/null 2>&1; then
  display_info="$(xrandr --current 2>&1 || true)"
else
  display_info="Neither wlr-randr nor xrandr is available; continuing without changing display settings."
fi
printf '%s\n' "$display_info"
if [[ "$display_info" != *"800x480"* && "$display_info" != *"800 x 480"* ]]; then
  echo "Warning: an active 800x480 mode was not detected. The installer will not change display settings." >&2
fi

echo "Touch devices:"
if command -v libinput >/dev/null 2>&1; then
  libinput list-devices 2>/dev/null | sed -n '/Touchscreen/,+8p' || true
else
  echo "libinput CLI is unavailable; the installer will not add it or change touch configuration."
fi

if ! command -v chromium >/dev/null 2>&1 && ! command -v chromium-browser >/dev/null 2>&1; then
  echo "Chromium is missing; installing only the browser package."
  sudo apt update
  if apt-cache show chromium >/dev/null 2>&1; then
    sudo apt install -y chromium
  elif apt-cache show chromium-browser >/dev/null 2>&1; then
    sudo apt install -y chromium-browser
  else
    echo "No Chromium package is available from the configured Raspberry Pi OS repositories." >&2
    exit 1
  fi
fi

mkdir -p "$autostart_dir" "$HOME/.local/share/pi-edge-assistant"
sed "s|@PROJECT_DIR@|$project_dir|g" "$project_dir/deploy/pi-edge-kiosk.desktop.in" >"$desktop_file"
chmod 644 "$desktop_file"

if command -v labwc >/dev/null 2>&1; then
  labwc_dir="$HOME/.config/labwc"
  labwc_autostart="$labwc_dir/autostart"
  launcher="$project_dir/scripts/start_kiosk.sh"
  mkdir -p "$labwc_dir"
  touch "$labwc_autostart"
  if ! grep -Fq "$launcher" "$labwc_autostart"; then
    printf '\n%s &\n' "$launcher" >>"$labwc_autostart"
  fi
fi

if command -v raspi-config >/dev/null 2>&1; then
  sudo raspi-config nonint do_boot_behaviour B4
fi

systemctl --user enable pi-edge-assistant.service
systemctl --user restart pi-edge-assistant.service

echo "Kiosk installed without changing DSI, touch, rotation, camera, model, swap, or fan settings."
echo "Reboot to verify automatic desktop login and kiosk startup: sudo reboot"
echo "Controls: $project_dir/scripts/kiosk_control.sh {pause|resume|restart|status|logs}"
