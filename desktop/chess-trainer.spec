# PyInstaller build of the desktop app, for Linux, Windows and macOS.
#   python3 docker/fetch_stockfish.py desktop   # this system's Stockfish into .cache/
#   uv run --group desktop pyinstaller --noconfirm desktop/chess-trainer.spec
# The result is a folder, dist/chess-trainer/, with the executable inside; on macOS also
# dist/Chess Trainer.app.
# One folder, not one file: a single file unpacks ~150 MB to a temp folder on every launch.
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
VERSION = re.search(r'__version__ = "(.+)"', (ROOT / "app" / "__init__.py").read_text()).group(1)
STOCKFISH = ROOT / ".cache" / ("stockfish.exe" if sys.platform == "win32" else "stockfish")
if not STOCKFISH.exists():
    sys.exit(f"missing {STOCKFISH}: run python3 docker/fetch_stockfish.py desktop first")

# The app finds its files next to app/ (app/config.py), so they keep their repo paths.
datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "openings"), "openings"),
    (str(ROOT / "catalog" / "data"), "catalog/data"),
    (str(ROOT / "catalog" / "SOURCE_COMMIT"), "catalog"),
    (str(ROOT / "evals"), "evals"),
    (str(ROOT / "app" / "engine" / "levels.toml"), "app/engine"),
    (str(ROOT / "app" / "db" / "migrations"), "app/db/migrations"),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "THIRD_PARTY_LICENSES.md"), "."),
    # Stockfish's build tag and its license and authors, as fetch_stockfish.py leaves them.
    *[(str(ROOT / ".cache" / name), "stockfish") for name in ("VERSION", "Copying.txt", "AUTHORS")],
    (str(ROOT / "desktop" / "icon.png"), "desktop"),
]

a = Analysis(
    [str(ROOT / "desktop" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[(str(STOCKFISH), "stockfish")],
    datas=datas,
    # uvicorn picks its loop and protocol modules by name at run time.
    hiddenimports=[
        {"linux": "desktop.qt_window", "darwin": "desktop.cocoa_window"}.get(sys.platform, "json"),
        *collect_submodules("uvicorn"),
    ],
    excludes=["tkinter", "pytest", "playwright", "PIL"],
)

# Qt brings QML modules, 3D, multimedia and ~50 languages the window never uses (~150 MB).
UNUSED_QT = re.compile(
    r"PyQt6/Qt6/(qml/"
    r"|lib/libQt6(Quick3D|QuickControls2|QuickDialogs2|QuickTemplates2|QuickEffects|QuickShapes"
    r"|QuickTimeline|QuickParticles|ShaderTools|Multimedia|Sensors|TextToSpeech|RemoteObjects"
    r"|Test|Pdf|SpatialAudio)"
    r"|translations/(?!qtwebengine_locales/(en-US|pt-BR|es|es-419)\.pak$"
    r"|(qt|qtbase|qtwebengine)_(en|pt_BR|es)\.qm$))"
)
a.binaries = [b for b in a.binaries if not UNUSED_QT.search(b[0].replace("\\", "/"))]
a.datas = [d for d in a.datas if not UNUSED_QT.search(d[0].replace("\\", "/"))]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="chess-trainer",
    console=False,
    # web/logo.svg at 1024 px; PyInstaller turns it into .ico (Windows) with Pillow.
    icon=str(ROOT / "desktop" / "icon.png"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="chess-trainer")

# macOS shows an icon and a name only for an .app bundle; Windows takes them from the .exe,
# Linux from a .desktop entry (desktop/README.md).
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Chess Trainer.app",
        icon=str(ROOT / "desktop" / "icon-macos.png"),  # with the margin of macOS's icon grid
        bundle_identifier="io.github.nielsencampos.chess-trainer",
        version=VERSION,
        info_plist={"CFBundleDisplayName": "Chess Trainer", "NSHighResolutionCapable": True},
    )
