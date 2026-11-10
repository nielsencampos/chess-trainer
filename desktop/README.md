# Desktop app (proof of concept)

The same app as the Docker image, in a native window: `launcher.py` starts the server on
`127.0.0.1:47800` and opens it with [pywebview](https://pywebview.flowrl.com/). Only Linux has
been built and tested so far.

## Run from source

```bash
scripts/extract-stockfish.sh       # Stockfish into .cache/ (needs the Docker image)
docker run --rm --entrypoint cat chess-trainer:local /opt/stockfish/VERSION > .cache/VERSION
uv sync --group desktop
uv run --group desktop python -m desktop.launcher
```

## Build

```bash
uv run --group desktop pyinstaller --noconfirm --distpath build/dist --workpath build/work desktop/chess-trainer.spec
build/dist/chess-trainer/chess-trainer
```

The result is a folder of about 625 MB, most of it Qt WebEngine (the window's browser engine),
Stockfish and DuckDB.

## Where things are

- Database, log and window storage: the user's data folder (`~/.local/share/chess-trainer` on
  Linux, `~/Library/Application Support/chess-trainer` on macOS, `%LOCALAPPDATA%\chess-trainer`
  on Windows).
- `CHESS_TRAINER_PORT`, `CHESS_TRAINER_DB` and `STOCKFISH_PATH` override the defaults.
- On Linux, `qt_window.py` saves downloads and prints, which pywebview's Qt backend does not do
  with Qt 6.

## Name and icon

The window is titled "Chess Trainer". The icon is the favicon's drawing, `web/logo.svg`, rendered
at 1024 px: `icon.png` full size, and `icon-macos.png` at 824 px inside a 1024 px canvas, the margin
of macOS's icon grid. To render them again:

```bash
inkscape web/logo.svg --export-type=png --export-width=1024 --export-filename=desktop/icon.png
inkscape web/logo.svg --export-type=png --export-width=824 --export-filename=/tmp/icon-824.png
magick /tmp/icon-824.png -background none -gravity center -extent 1024x1024 -strip desktop/icon-macos.png
```

- Windows: PyInstaller turns `icon.png` into the `.exe` icon (Pillow is needed at build time).
- macOS: the spec builds `Chess Trainer.app` with `icon-macos.png` as `.icns`.
- Linux: GNOME and other Wayland desktops take the icon from a `.desktop` entry, not from the
  window. For a local build, `~/.local/share/applications/chess-trainer.desktop`:

  ```ini
  [Desktop Entry]
  Type=Application
  Name=Chess Trainer
  Exec=/path/to/chess-trainer/chess-trainer
  Icon=/path/to/chess-trainer/_internal/desktop/icon.png
  StartupWMClass=chess-trainer
  Categories=Game;BoardGame;
  ```

## Not done yet

- Builds for Windows and macOS, in CI, published on the Release, and install instructions for
  players.
- The bundled Qt, PyQt6 and pywebview licenses in `THIRD_PARTY_LICENSES.md`, before anything is
  distributed.
- A second launch opens a second window on the first one's server instead of focusing the first.
