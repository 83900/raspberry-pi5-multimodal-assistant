#!/usr/bin/env bash
set -euo pipefail

data_dir="${EDGE_DATA_DIR:-$HOME/.local/share/pi-edge-assistant}"
profile_dir="$data_dir/kiosk-profile"
pause_file="$data_dir/kiosk.paused"
log_file="$data_dir/kiosk.log"
action="${1:-status}"

stop_browser() {
  pkill -u "$(id -u)" -f -- "--user-data-dir=$profile_dir" 2>/dev/null || true
}

case "$action" in
  pause)
    mkdir -p "$data_dir"
    touch "$pause_file"
    stop_browser
    echo "Kiosk paused. The assistant backend remains active."
    ;;
  resume)
    rm -f "$pause_file"
    echo "Kiosk resumed. Chromium will reopen within a few seconds."
    ;;
  restart)
    rm -f "$pause_file"
    stop_browser
    echo "Kiosk browser restart requested."
    ;;
  status)
    if [[ -f "$pause_file" ]]; then
      echo "paused"
    elif pgrep -u "$(id -u)" -f -- "--user-data-dir=$profile_dir" >/dev/null 2>&1; then
      echo "running"
    else
      echo "not running"
    fi
    ;;
  logs)
    touch "$log_file"
    tail -n 100 -f "$log_file"
    ;;
  *)
    echo "Usage: $0 {pause|resume|restart|status|logs}" >&2
    exit 2
    ;;
esac
