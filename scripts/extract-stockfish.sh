#!/usr/bin/env bash
# Copies the Stockfish binary out of the image, for engine tests and local development.
# Usage: scripts/extract-stockfish.sh [IMAGE]
set -euo pipefail

# The image's binary is built for Linux: on macOS or Windows it would not run.
if [[ "$(uname -s)" != Linux ]]; then
  echo "The image's Stockfish runs on Linux only; use: python3 docker/fetch_stockfish.py desktop" >&2
  exit 1
fi
image="${1:-chess-trainer:local}"
mkdir -p .cache
container="$(docker create "$image")"
trap 'docker rm "$container" >/dev/null' EXIT
docker cp "$container:/opt/stockfish/stockfish" .cache/stockfish
echo ".cache/stockfish ($(docker run --rm --entrypoint cat "$image" /opt/stockfish/VERSION))"
