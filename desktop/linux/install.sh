#!/usr/bin/env sh
# Installs Chess Trainer for the current user, from the folder this script is in.
#   ./install.sh               copy the app to ~/.local/opt/chess-trainer and add it to the menu
#   ./install.sh --uninstall   remove the app and its menu entry (your games and lines stay)
# Nothing needs root. The data (database, log) lives in ~/.local/share/chess-trainer and is
# never touched here.
set -eu

here="$(cd "$(dirname "$0")" && pwd)"
data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
target="$HOME/.local/opt/chess-trainer"
entry="$data_home/applications/chess-trainer.desktop"

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$target"
    rm -f "$entry"
    command -v update-desktop-database >/dev/null 2>&1 &&
        update-desktop-database "$data_home/applications" || true
    echo "Chess Trainer removed. Your games and lines are still in $data_home/chess-trainer."
    exit 0
fi

if [ ! -x "$here/chess-trainer" ]; then
    echo "Run this script from the unpacked chess-trainer folder." >&2
    exit 1
fi

if [ "$here" != "$target" ]; then
    rm -rf "$target"
    mkdir -p "$(dirname "$target")"
    cp -R "$here" "$target"
fi

mkdir -p "$(dirname "$entry")"
cat >"$entry" <<EOF
[Desktop Entry]
Type=Application
Name=Chess Trainer
Comment=Opening trainer with Stockfish
Exec="$target/chess-trainer"
Icon=$target/_internal/desktop/icon.png
StartupWMClass=chess-trainer
Categories=Game;BoardGame;
Terminal=false
EOF
command -v update-desktop-database >/dev/null 2>&1 &&
    update-desktop-database "$data_home/applications" || true
echo "Chess Trainer installed in $target. Open it from your applications menu."
