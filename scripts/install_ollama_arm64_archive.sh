#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
archive="${1:-$project_dir/ollama-linux-arm64.tgz}"

if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "This installer is only for Linux ARM64/aarch64." >&2
  exit 1
fi
if [[ ! -f "$archive" ]]; then
  echo "Archive not found: $archive" >&2
  exit 1
fi
if systemctl cat ollama.service >/dev/null 2>&1; then
  echo "An Ollama service already exists; audit or update it instead of overwriting it." >&2
  exit 1
fi

sudo tar -C /usr -xzf "$archive"
if ! id ollama >/dev/null 2>&1; then
  sudo useradd --system --create-home --home-dir /usr/share/ollama --shell /usr/sbin/nologin ollama
fi
sudo install -m 0644 "$project_dir/deploy/ollama.service" /etc/systemd/system/ollama.service
sudo systemctl daemon-reload
sudo systemctl enable --now ollama.service
ollama --version
systemctl status ollama.service --no-pager
