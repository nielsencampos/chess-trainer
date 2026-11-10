#!/usr/bin/env bash
# Starts a local LanguageTool server for scripts/check_text.py, on 127.0.0.1:8081.
#
# Downloads the official standalone release into .cache/ once (checking its SHA-256), then runs
# it with Java 17 or newer. LanguageTool is LGPL-2.1; it is a development tool and never ships in
# the image or the desktop app.
#
#   scripts/languagetool.sh               # in the foreground, Ctrl+C stops it
#   scripts/languagetool.sh --background  # returns once the server answers
set -euo pipefail

VERSION=6.6
SHA256=53600506b399bb5ffe1e4c8dec794fd378212f14aaf38ccef9b6f89314d11631
PORT="${LANGUAGETOOL_PORT:-8081}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/.cache/LanguageTool-$VERSION"

if [[ ! -f "$DIR/languagetool-server.jar" ]]; then
  mkdir -p "$ROOT/.cache"
  zip="$ROOT/.cache/LanguageTool-$VERSION.zip"
  curl -fsSL -o "$zip" "https://languagetool.org/download/LanguageTool-$VERSION.zip"
  echo "$SHA256  $zip" | sha256sum -c --quiet
  unzip -q "$zip" -d "$ROOT/.cache"
  rm "$zip"
fi

cmd=(java -cp "$DIR/languagetool-server.jar" org.languagetool.server.HTTPServer --port "$PORT")
if [[ "${1:-}" != "--background" ]]; then
  exec "${cmd[@]}"
fi
"${cmd[@]}" > "$ROOT/.cache/languagetool.log" 2>&1 &
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$PORT/v2/languages" > /dev/null 2>&1; then
    echo "LanguageTool $VERSION on http://127.0.0.1:$PORT"
    exit 0
  fi
  sleep 1
done
echo "LanguageTool did not start; see .cache/languagetool.log" >&2
exit 1
