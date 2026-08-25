#!/usr/bin/env bash
set -u

output_dir="${1:-$PWD/audit}"
mkdir -p "$output_dir"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
report="$output_dir/pi-audit-$timestamp.txt"

run() {
  local title="$1"
  shift
  {
    echo
    echo "## $title"
    echo '$' "$@"
    "$@" 2>&1 || true
  } >>"$report"
}

{
  echo "# Raspberry Pi Edge Assistant audit"
  echo "generated_utc=$timestamp"
  echo "hostname=$(hostname)"
} >"$report"

run "OS release" cat /etc/os-release
run "Kernel" uname -a
run "Architecture" dpkg --print-architecture
run "Pi model" sh -c 'tr -d "\\0" </proc/device-tree/model'
run "CPU" lscpu
run "Memory" free -h
run "Swap devices" swapon --show --bytes --output=NAME,TYPE,SIZE,USED,PRIO
run "Filesystems" findmnt -o TARGET,SOURCE,FSTYPE,OPTIONS
run "Disk usage" df -hT
run "Swapfile mount" findmnt --target /mnt/swapfile
run "Temperature" vcgencmd measure_temp
run "Throttle flags" vcgencmd get_throttled
run "USB devices" lsusb
run "Capture devices" arecord -l
run "Capture PCMs" arecord -L
run "Playback devices" aplay -l
run "Playback PCMs" aplay -L
run "Camera list" rpicam-hello --list-cameras
run "Camera version" rpicam-hello --version
run "Ollama version" ollama --version
run "Ollama models" ollama list
run "Ollama service" systemctl status ollama --no-pager
run "Ollama unit" systemctl cat ollama
run "Whisper executables" sh -c 'find "$HOME" -path "*/whisper.cpp/build/bin/whisper-cli" -o -path "*/whisper.cpp/main" 2>/dev/null'
run "Python" python3 --version
run "Network listeners" ss -lntup

echo "$report"
