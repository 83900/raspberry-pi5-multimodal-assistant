#!/usr/bin/env bash
set -euo pipefail

runtime_dir="$(mktemp -d)"
cleanup() { rm -rf "$runtime_dir"; }
trap cleanup EXIT

echo "Testing camera..."
rpicam-still --nopreview --immediate --width 1024 --height 768 -o "$runtime_dir/camera.jpg"
test -s "$runtime_dir/camera.jpg"

echo "Testing five-second microphone capture..."
arecord -q -D "${AUDIO_CAPTURE_DEVICE:-default}" -d 5 -f S16_LE -r 16000 -c 1 "$runtime_dir/microphone.wav"
test -s "$runtime_dir/microphone.wav"

echo "Playing microphone sample..."
aplay -q -D "${AUDIO_PLAYBACK_DEVICE:-default}" "$runtime_dir/microphone.wav"

echo "Temperature and throttle state:"
vcgencmd measure_temp || true
vcgencmd get_throttled || true
echo "Hardware smoke test passed."
