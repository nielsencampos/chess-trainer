"""Desktop launcher: runs the app's server on loopback and shows it in a native window.

Proof of concept (Linux first). Run from source with `uv run --group desktop python -m
desktop.launcher`, or build it with `uv run --group desktop pyinstaller desktop/chess-trainer.spec`.
The data lives in the user's data folder, never next to the executable.
"""

import json
import logging
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import platformdirs
import uvicorn
import webview

APP_NAME = "chess-trainer"
HOST = "127.0.0.1"
# A fixed port, because the UI preferences are kept in localStorage, which belongs to an origin.
DEFAULT_PORT = 47800
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))


class LaunchError(RuntimeError):
    """The app cannot start, such as when another program holds its port."""


def configure(data_dir: Path) -> None:
    """Points the app's settings at the user's data folder and the bundled Stockfish.

    A variable that is already set wins, so a developer can still choose their own files.

    Args:
        data_dir (Path): The user's data folder for the app.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("CHESS_TRAINER_DB", str(data_dir / "chess-trainer.duckdb"))
    stockfish = BUNDLE / "stockfish" / ("stockfish.exe" if os.name == "nt" else "stockfish")
    if not stockfish.exists():  # from source: the binary copied by scripts/extract-stockfish.sh
        stockfish = BUNDLE / ".cache" / stockfish.name
    os.environ.setdefault("STOCKFISH_PATH", str(stockfish))
    os.environ.setdefault("STOCKFISH_VERSION_FILE", str(stockfish.parent / "VERSION"))


def unblock_bundle() -> int:
    """Removes the "downloaded from the internet" mark from the app's own files (Windows).

    A browser marks a downloaded zip with a `Zone.Identifier` stream, and Explorer copies the
    mark to every file it extracts. .NET Framework then refuses to load the marked
    `Python.Runtime.dll`, and pywebview's window cannot start. This runs before pywebview
    loads .NET. It does nothing outside a frozen Windows build, and skips files it cannot change.

    Returns:
        int: How many files had the mark.
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return 0
    unblocked = 0
    for folder, _, files in os.walk(BUNDLE):
        for name in files:
            try:
                os.remove(os.path.join(folder, name) + ":Zone.Identifier")
                unblocked += 1
            except OSError:
                pass  # no mark, or a read-only install
    return unblocked


def running_here(port: int) -> bool:
    """Tells whether chess-trainer already answers on the port.

    Args:
        port (int): The port on loopback.

    Returns:
        bool: True if the app answers, False if nothing listens there.

    Raises:
        LaunchError: Another program answers on the port.
    """
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/health", timeout=2) as response:
            json.loads(response.read())["engine"]
            return True
    except urllib.error.HTTPError as error:
        raise LaunchError(f"port {port} is used by another program") from error
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        # Nothing answers. Windows may time out on a closed loopback port instead of refusing.
        # If a program holds the port without answering, the server fails to bind it instead.
        return False
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise LaunchError(f"port {port} is used by another program") from error


def start_server(port: int) -> tuple[uvicorn.Server, threading.Thread]:
    """Starts the app's server in a thread and waits until it serves.

    Args:
        port (int): The port on loopback.

    Returns:
        tuple[uvicorn.Server, threading.Thread]: The server and its thread.

    Raises:
        LaunchError: The server stopped before serving, such as on a bad database.
    """
    from app.main import create_app  # after configure(): the settings are read here

    # One worker, as in the image: DuckDB allows one writing process per file.
    config = uvicorn.Config(create_app(), host=HOST, port=port, workers=1, log_config=None)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="server", daemon=True)
    thread.start()
    while not server.started:
        thread.join(0.05)
        if not thread.is_alive():
            raise LaunchError("the server stopped while starting; see the log")
    return server, thread


def main() -> None:
    """Opens the window, starting the server first unless this app already runs."""
    data_dir = Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))
    configure(data_dir)
    logging.basicConfig(
        filename=data_dir / f"{APP_NAME}.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if unblocked := unblock_bundle():
        logging.info("removed the downloaded-file mark from %d files", unblocked)
    port = int(os.environ.get("CHESS_TRAINER_PORT", DEFAULT_PORT))
    server = thread = None
    # shortcut: a second launch opens another window on the first one's server, and that
    # window stops working when the first one closes. Focus the first window instead later.
    if not running_here(port):
        server, thread = start_server(port)

    linux = sys.platform == "linux"
    # On Linux our own Qt handlers save downloads and print (desktop/qt_window.py).
    webview.settings["ALLOW_DOWNLOADS"] = not linux
    window = webview.create_window(
        "Chess Trainer", f"http://{HOST}:{port}/", width=1280, height=800, min_size=(1280, 720)
    )
    if sys.platform == "darwin":
        from desktop.cocoa_window import install

        install()  # print with the Scoresheet's own margins (desktop/cocoa_window.py)
    hooks = None
    if linux:
        from desktop.qt_window import connect_hooks

        hooks = connect_hooks
    webview.start(
        hooks,
        window,
        # Qt ships as wheels and needs no system packages; GTK would need PyGObject built.
        gui="qt" if linux else None,
        private_mode=False,  # keep localStorage (UI preferences) between launches
        storage_path=str(data_dir / "webview"),
        # Linux only: Windows takes the icon from the .exe, and its form throws on a PNG icon
        # (System.Drawing.Icon reads .ico only); macOS takes it from the .app.
        icon=str(BUNDLE / "desktop" / "icon.png") if linux else None,
    )
    if server is not None:
        server.should_exit = True  # the lifespan stops Stockfish and closes the database
        thread.join(10)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # A windowed build has no console: the log is where a failed launch can be read.
        logging.exception("the app could not start")
        raise
