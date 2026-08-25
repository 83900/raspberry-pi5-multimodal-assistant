#!/usr/bin/env bash
set -euo pipefail

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed. Use the official ARM64 installer/manual package first." >&2
  exit 1
fi

ollama pull qwen3.5:2b
if [[ "${1:-}" == "--compare" ]]; then
  ollama pull qwen3.5:4b
fi
ollama list
