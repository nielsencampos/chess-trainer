#!/usr/bin/env bash
# Runs Vale with the project's style (.vale.ini) on the docs, the README and the UI strings.
#
# Downloads the pinned Vale release for this system into .cache/bin once, checking it against the
# release's checksums. The UI strings and the README's pt-BR and es sections are exported to
# .cache/vale first (scripts/check_text.py --export), so each gets the rules of its language.
#
#   scripts/vale.sh
set -euo pipefail

VERSION=3.26.0
CHECKSUMS_SHA256=b5febf58cb2cd515a1b98dde463fdf4c5796efda0b4d698374c2dac9d4c73638
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$ROOT/.cache/bin/vale"
cd "$ROOT"

if [[ ! -x "$BIN" ]] || ! "$BIN" --version | grep -q " $VERSION$"; then
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) asset="Linux_64-bit.tar.gz" ;;
    Linux-aarch64 | Linux-arm64) asset="Linux_arm64.tar.gz" ;;
    Darwin-x86_64) asset="macOS_64-bit.tar.gz" ;;
    Darwin-arm64) asset="macOS_arm64.tar.gz" ;;
    *) echo "No Vale release for $(uname -s) $(uname -m)" >&2; exit 1 ;;
  esac
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  url="https://github.com/errata-ai/vale/releases/download/v$VERSION"
  curl -fsSL -o "$tmp/checksums.txt" "$url/vale_${VERSION}_checksums.txt"
  echo "$CHECKSUMS_SHA256  $tmp/checksums.txt" | shasum -a 256 -c --quiet
  curl -fsSL -o "$tmp/vale_${VERSION}_$asset" "$url/vale_${VERSION}_$asset"
  (cd "$tmp" && grep " vale_${VERSION}_$asset\$" checksums.txt | shasum -a 256 -c --quiet)
  tar xzf "$tmp/vale_${VERSION}_$asset" -C "$tmp" vale
  mkdir -p "$(dirname "$BIN")"
  mv "$tmp/vale" "$BIN"
fi

rm -rf .cache/vale
uv run python scripts/check_text.py --export .cache/vale
"$BIN" --output=line docs/*.md HOW_TO_INSTALL*.md README.md .cache/vale/*.md
echo "No style errors."
