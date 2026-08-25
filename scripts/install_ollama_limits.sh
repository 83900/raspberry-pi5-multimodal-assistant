#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sudo install -d -m 0755 /etc/systemd/system/ollama.service.d
sudo install -m 0644 "$project_dir/deploy/ollama-edge.conf" /etc/systemd/system/ollama.service.d/edge.conf
sudo systemctl daemon-reload
sudo systemctl restart ollama
systemctl status ollama --no-pager
