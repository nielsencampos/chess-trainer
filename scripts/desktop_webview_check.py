"""Checks a PGN download and the Scoresheet print in pywebview's macOS window (WKWebView).

Usage: uv run --group desktop python scripts/desktop_webview_check.py [OUT_DIR]

Runs the app from source, as desktop/launcher.py does, on a temporary database, and drives the real
page: it exports the lines of one opening as PGN and presses the Scoresheet's print button. Only
the two modal dialogs are replaced, since CI cannot click them: the save panel by a fixed path
(OUT_DIR/lines.pgn) and the print panel by a print to PDF on A4 (OUT_DIR/scoresheet.pdf), with the
app's own page setup (desktop/cocoa_window.py). Everything else is the real path: the
`<a download>` click becomes a WKDownload, and `window.print()` goes through pywebview's script
message to a print operation of the web view. macOS only.
"""

import json
import os
import sys
import tempfile
import threading
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 47801  # not the app's port, so a running app does not get in the way
TIMEOUT_S = 60
WATCHDOG_S = 300  # a stuck modal or event must not hold the CI job until its own timeout


def wait_for(window: object, script: str, what: str) -> None:
    """Waits until a script returns true in the page.

    Args:
        window (object): The pywebview window.
        script (str): A JavaScript expression.
        what (str): What is awaited, for the error.

    Raises:
        TimeoutError: The expression stayed false for `TIMEOUT_S`.
    """
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        if window.evaluate_js(script):
            return
        time.sleep(0.5)
    raise TimeoutError(what)


def wait_file(path: Path, what: str) -> None:
    """Waits until a file exists and has stopped growing.

    Args:
        path (Path): The file.
        what (str): What is awaited, for the error.

    Raises:
        TimeoutError: The file did not appear within `TIMEOUT_S`.
    """
    deadline = time.monotonic() + TIMEOUT_S
    size = -1
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size > 0 and path.stat().st_size == size:
            return
        size = path.stat().st_size if path.exists() else -1
        time.sleep(1)
    raise TimeoutError(what)


def main(out_dir: Path) -> int:
    """Runs the checks and reports them.

    Args:
        out_dir (Path): Where the PGN and the PDF are written; it must not hold them yet.

    Returns:
        int: 0 if both checks pass, 1 otherwise.
    """
    if sys.platform != "darwin":
        print("this check is for macOS (WKWebView) only")
        return 1
    import AppKit
    import Foundation
    import Quartz
    import webview
    from webview.platforms.cocoa import BrowserView

    sys.path.insert(0, str(ROOT))
    from desktop import cocoa_window, launcher

    out_dir.mkdir(parents=True, exist_ok=True)
    pgn, pdf = out_dir / "lines.pgn", out_dir / "scoresheet.pdf"
    for path in (pgn, pdf):
        path.unlink(missing_ok=True)
    result: dict = {}

    class CheckDownloadDelegate(AppKit.NSObject):
        """The download delegate of pywebview, with a fixed path instead of the save panel."""

        def download_decideDestinationUsingResponse_suggestedFilename_completionHandler_(
            self, download, response, suggested, handler
        ):
            """Saves the download to `pgn`, recording the name the page suggested."""
            result["suggested"] = str(suggested)
            handler(Foundation.NSURL.fileURLWithPath_(str(pgn)))

        def download_didFailWithError_resumeData_(self, download, error, data):
            """Records a failed download."""
            result["download_error"] = str(error)

    def print_to_pdf(web_view: object) -> None:
        """The app's print (desktop/cocoa_window.py), to a PDF instead of through the panel.

        Args:
            web_view (object): The WKWebView.
        """
        result["print_called"] = True
        info = cocoa_window.print_info()
        # A4, as the Scoresheet's hint asks; the runner's default paper is US Letter.
        info.setPaperSize_(Foundation.NSMakeSize(595.28, 841.89))
        info.setJobDisposition_(AppKit.NSPrintSaveJob)
        info.dictionary()[AppKit.NSPrintJobSavingURL] = Foundation.NSURL.fileURLWithPath_(str(pdf))
        result["margins_pt"] = [
            round(margin, 1)
            for margin in (
                info.topMargin(),
                info.rightMargin(),
                info.bottomMargin(),
                info.leftMargin(),
            )
        ]
        operation = cocoa_window.print_operation(web_view, info)
        operation.setShowsPrintPanel_(False)
        operation.setShowsProgressPanel_(False)
        operation.runOperationModalForWindow_delegate_didRunSelector_contextInfo_(
            web_view.window(), None, None, None
        )

    BrowserView.DownloadDelegate = CheckDownloadDelegate
    BrowserView.print_webview = staticmethod(print_to_pdf)

    data_dir = Path(tempfile.mkdtemp(prefix="chess-trainer-check-"))
    os.environ["CHESS_TRAINER_DB"] = str(data_dir / "chess-trainer.duckdb")
    launcher.configure(data_dir)
    server, thread = launcher.start_server(PORT)

    def checks(window: webview.Window) -> None:
        """Drives the page, then closes the window.

        Args:
            window (webview.Window): The pywebview window.
        """
        try:
            window.events.loaded.wait(TIMEOUT_S)
            wait_for(window, "!document.getElementById('tab-openings').disabled", "the menu")
            window.evaluate_js("document.getElementById('tab-openings').click()")
            wait_for(window, "!!document.querySelector('.opening-check')", "the openings list")
            window.evaluate_js(
                "document.querySelector('.opening-check').click();"
                "document.getElementById('lines-export').click()"
            )
            wait_file(pgn, "the PGN download")
            window.evaluate_js("document.getElementById('tab-scoresheet').click()")
            wait_for(window, "!document.getElementById('sheet-page').hidden", "the Scoresheet")
            window.evaluate_js("document.getElementById('sheet-print').click()")
            wait_file(pdf, "the Scoresheet PDF")
        except TimeoutError as error:
            result["timeout"] = f"no {error} after {TIMEOUT_S} s"
        finally:
            window.destroy()

    def stuck() -> None:
        """Ends the process when the checks hang, such as on a modal nobody closes."""
        print(f"FAIL: stuck after {WATCHDOG_S} s: {json.dumps(result)}", flush=True)
        os._exit(1)

    watchdog = threading.Timer(WATCHDOG_S, stuck)
    watchdog.daemon = True
    watchdog.start()
    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window(
        "Chess Trainer", f"http://127.0.0.1:{PORT}/", width=1280, height=800
    )
    webview.start(checks, window, private_mode=True)
    server.should_exit = True
    thread.join(10)

    failures = [result[key] for key in ("timeout", "download_error") if key in result]
    if pgn.exists():
        text = pgn.read_text(encoding="utf-8")
        result["pgn_bytes"] = len(text)
        if not (text.startswith("[") and "1." in text):
            failures.append("the PGN does not look like PGN")
    else:
        failures.append("no PGN was saved")
    if not result.get("print_called"):
        failures.append("window.print() did not reach pywebview's print handler")
    if pdf.exists():
        document = Quartz.PDFDocument.alloc().initWithURL_(
            Foundation.NSURL.fileURLWithPath_(str(pdf))
        )
        text = str(document.string() or "") if document else ""
        result["pdf_pages"] = document.pageCount() if document else 0
        headings = [
            json.loads(path.read_text(encoding="utf-8"))["sheet.heading"]
            for path in (ROOT / "web" / "i18n").glob("*.json")
        ]

        # The heading may be set in capitals by CSS, and the PDF's text keeps them.
        def flat(value: str) -> str:
            """Folds case, accents' encoding and spacing, to compare PDF text with the page's.

            Args:
                value (str): A text.

            Returns:
                str: The folded text.
            """
            return " ".join(unicodedata.normalize("NFC", value).split()).casefold()

        result["pdf_heading_found"] = any(flat(heading) in flat(text) for heading in headings)
        if result["pdf_pages"] != 1 or not result["pdf_heading_found"]:
            failures.append("the Scoresheet is not one A4 page with its heading")
    else:
        failures.append("no Scoresheet PDF was written")

    print(json.dumps(result, indent=2))
    for failure in failures:
        print(f"FAIL: {failure}")
    if not failures:
        print(f"ok: PGN download and Scoresheet print work in WKWebView ({out_dir})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "webview-check"))
