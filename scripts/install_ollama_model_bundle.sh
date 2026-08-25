#!/usr/bin/env bash
set -euo pipefail

bundle="${1:-}"
models_dir="${2:-/usr/share/ollama/.ollama/models}"

if [[ -z "$bundle" || ! -d "$bundle/blobs" || ! -d "$bundle/manifests" ]]; then
  echo "Usage: $0 BUNDLE_DIR [OLLAMA_MODELS_DIR]" >&2
  exit 1
fi

sudo install -d -m 0755 "$models_dir/blobs" "$models_dir/manifests"
sudo cp -a "$bundle/blobs/." "$models_dir/blobs/"
sudo cp -a "$bundle/manifests/." "$models_dir/manifests/"
if id ollama >/dev/null 2>&1; then
  sudo chown -R ollama:ollama "$models_dir"
fi
sudo systemctl restart ollama
ollama list
