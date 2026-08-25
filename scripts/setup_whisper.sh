#!/usr/bin/env bash
set -euo pipefail

whisper_dir="${WHISPER_DIR:-$HOME/whisper.cpp}"
models=(base small)

if [[ ! -d "$whisper_dir/.git" ]]; then
  git clone https://github.com/ggml-org/whisper.cpp.git "$whisper_dir"
else
  git -C "$whisper_dir" pull --ff-only
fi

cmake -S "$whisper_dir" -B "$whisper_dir/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$whisper_dir/build" --config Release -j "$(nproc)"

for model in "${models[@]}"; do
  "$whisper_dir/models/download-ggml-model.sh" "$model"
  source_model="$whisper_dir/models/ggml-$model.bin"
  quantized_model="$whisper_dir/models/ggml-$model-q5_0.bin"
  if [[ ! -f "$quantized_model" ]]; then
    "$whisper_dir/build/bin/quantize" "$source_model" "$quantized_model" q5_0
  fi
done

echo "Whisper models ready in $whisper_dir/models"
