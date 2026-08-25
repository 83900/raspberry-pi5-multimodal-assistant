#!/usr/bin/env bash
set -euo pipefail

backup_root="${1:-$HOME/pi-edge-backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$backup_root/$timestamp"
mkdir -p "$target/config" "$target/scripts"

if [[ -f /etc/systemd/system/ollama.service ]]; then
  cp /etc/systemd/system/ollama.service "$target/config/"
fi
if [[ -d /etc/systemd/system/ollama.service.d ]]; then
  cp -a /etc/systemd/system/ollama.service.d "$target/config/"
fi
if [[ -f /etc/fstab ]]; then
  cp /etc/fstab "$target/config/fstab"
fi

ollama list >"$target/ollama-models.txt" 2>&1 || true
systemctl cat ollama >"$target/ollama-unit.txt" 2>&1 || true
swapon --show >"$target/swap.txt" 2>&1 || true

find "$HOME" -maxdepth 3 \
  -path "$backup_root" -prune -o \
  -type f \( -name '*.py' -o -name '*.service' -o -name '*.sh' \) \
  -not -path '*/.cache/*' -not -path '*/.venv/*' -not -path '*/models/*' -print0 |
  while IFS= read -r -d '' file; do
    relative="${file#"$HOME"/}"
    destination="$target/scripts/$relative"
    mkdir -p "$(dirname "$destination")"
    cp "$file" "$destination"
  done

tar -C "$backup_root" -czf "$backup_root/pi-edge-environment-$timestamp.tar.gz" "$timestamp"
echo "$backup_root/pi-edge-environment-$timestamp.tar.gz"
