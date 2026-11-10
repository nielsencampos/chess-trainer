# Desktop app (proof of concept)

The same app as the Docker image, in a native window: `launcher.py` starts the server on
`127.0.0.1:47800` and opens it with [pywebview](https://pywebview.flowrl.com/): Qt WebEngine on
Linux, WebView2 on Windows and WKWebView on macOS. Players install it as described in
[HOW_TO_INSTALL.md](../HOW_TO_INSTALL.md).

## Run from source

```bash
python3 docker/fetch_stockfish.py desktop   # this system's Stockfish, VERSION and license into .cache/
uv sync --group desktop
uv run --group desktop python -m desktop.launcher
```

## Build

```bash
uv run --group desktop pyinstaller --noconfirm --distpath build/dist --workpath build/work desktop/chess-trainer.spec
build/dist/chess-trainer/chess-trainer
```

The result is a folder of about 625 MB on Linux, most of it Qt WebEngine (the window's browser
engine), Stockfish and DuckDB. On macOS PyInstaller also makes `build/dist/Chess Trainer.app`.

On macOS, where nobody here can try it by hand, CI also runs `scripts/desktop_webview_check.py`:
from source, it exports a PGN and prints the Scoresheet in the real WKWebView window, with only the
save and print panels replaced (by a fixed path and a print to PDF), and checks the files. The PGN
and PDF are kept as the job's `webview-check-*` artifact.

`scripts/desktop_smoke.py EXECUTABLE` starts a build, checks `/api/health` (with the bundled
Stockfish) and that the window stays up, and closes it.

## CI and releases

`.github/workflows/desktop.yml` builds and smoke-checks on Ubuntu 22.04 (the oldest glibc we
support), Windows, macOS on Apple Silicon and macOS on Intel. On a `v*` tag it uploads the packages
to a draft GitHub Release, published by hand:

- `chess-trainer-<tag>-linux-x86_64.tar.gz`: the folder plus `install.sh`, which copies it to
  `~/.local/opt/chess-trainer` and writes the `.desktop` entry (`--uninstall` removes both).
- `chess-trainer-<tag>-windows-x64.zip`: the folder with `chess-trainer.exe`.
- `chess-trainer-<tag>-macos-arm64.zip` and `-macos-intel.zip`: `Chess Trainer.app`, signed ad hoc
  (not notarized). Stockfish's macOS build is universal; Python and the bundle are per architecture.

Nothing is signed with a paid certificate, so SmartScreen and Gatekeeper warn on the first launch
(HOW_TO_INSTALL.md explains how to get past them).

## Where things are

- Database, log and window storage: the user's data folder (`~/.local/share/chess-trainer` on
  Linux, `~/Library/Application Support/chess-trainer` on macOS, `%LOCALAPPDATA%\chess-trainer`
  on Windows).
- `CHESS_TRAINER_PORT`, `CHESS_TRAINER_DB` and `STOCKFISH_PATH` override the defaults.
- On Linux, `qt_window.py` saves downloads and prints, which pywebview's Qt backend does not do
  with Qt 6. On Windows (WebView2) and macOS (WKWebView) pywebview handles both: a download asks
  where to save, and `window.print()` opens the system print dialog. On macOS `cocoa_window.py`
  replaces pywebview's page setup: WKWebView ignores CSS `@page` margins, and the printer's
  printable area left the A4 Scoresheet too little room, so it prints with the sheet's 10 mm.
- On Windows the window gets no `icon`: the `.exe` has it, and pywebview's form throws on a PNG. WebKit reads a blob download
  after the click, so `web/js/download.js` revokes the blob's URL a minute later, not at once.
- On Windows, Stockfish starts with `CREATE_NO_WINDOW` (`app/engine/process.py`), or the windowed
  app would open a console for it.

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
  window. `linux/install.sh` writes it; by hand, for a local build, `~/.local/share/applications/chess-trainer.desktop`:

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

- Signing with paid certificates (Windows Authenticode, Apple notarization), and an installer.
- A Linux arm64 build.
- A second launch opens a second window on the first one's server instead of focusing the first.
