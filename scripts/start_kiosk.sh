#!/usr/bin/env bash
set -euo pipefail

if [[ "$EUID" -eq 0 ]]; then
  echo "Do not run the kiosk browser as root." >&2
  exit 1
fi

data_dir="${EDGE_DATA_DIR:-$HOME/.local/share/pi-edge-assistant}"
runtime_dir="${XDG_RUNTIME_DIR:-/tmp}/pi-edge-assistant"
profile_dir="$data_dir/kiosk-profile"
pause_file="$data_dir/kiosk.paused"
log_file="$data_dir/kiosk.log"
kiosk_url="${KIOSK_URL:-http://127.0.0.1:8080/?display=1}"

mkdir -p "$data_dir" "$runtime_dir" "$profile_dir"
chmod 700 "$data_dir" "$runtime_dir" "$profile_dir"
exec 9>"$runtime_dir/kiosk.lock"
if ! flock -n 9; then
  exit 0
fi

find_browser() {
  if [[ -n "${KIOSK_BROWSER:-}" && -x "${KIOSK_BROWSER}" ]]; then
    printf '%s\n' "$KIOSK_BROWSER"
    return 0
  fi
  command -v chromium 2>/dev/null || command -v chromium-browser 2>/dev/null
}

browser="$(find_browser || true)"
if [[ -z "$browser" ]]; then
  echo "Chromium is not installed. Run scripts/install_kiosk.sh first." | tee -a "$log_file" >&2
  exit 1
fi

wait_for_backend() {
  until curl -fsS --max-time 2 http://127.0.0.1:8080/api/health >/dev/null 2>&1; do
    if [[ -f "$pause_file" ]]; then
      return 1
    fi
    sleep 2
  done
}

browser_args=(
  "--user-data-dir=$profile_dir"
  "--kiosk"
  "--no-first-run"
  "--no-default-browser-check"
  "--noerrdialogs"
  "--disable-session-crashed-bubble"
  "--disable-pinch"
  "--overscroll-history-navigation=0"
  "--autoplay-policy=no-user-gesture-required"
  "--password-store=basic"
  "--disable-features=Translate"
)
if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
  browser_args+=("--ozone-platform=wayland")
fi

while true; do
  if [[ -f "$pause_file" ]]; then
    sleep 2
    continue
  fi
  if ! wait_for_backend; then
    continue
  fi
  if [[ -n "${DISPLAY:-}" ]] && command -v xset >/dev/null 2>&1; then
    xset s off >/dev/null 2>&1 || true
    xset -dpms >/dev/null 2>&1 || true
  fi
  printf '%s starting Chromium kiosk\n' "$(date --iso-8601=seconds)" >>"$log_file"
  "$browser" "${browser_args[@]}" "$kiosk_url" >>"$log_file" 2>&1 || true
  printf '%s Chromium exited; retrying in 3 seconds\n' "$(date --iso-8601=seconds)" >>"$log_file"
  sleep 3
done
