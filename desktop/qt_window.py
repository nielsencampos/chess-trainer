"""Downloads and printing for pywebview's Qt window (Linux).

pywebview's Qt backend saves a download with a Qt5-only call and under the blob's random name,
and nothing answers `window.print()`. These handlers replace both.
"""

from pathlib import Path

import webview
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest
from PyQt6.QtWidgets import QDialog, QFileDialog


class WindowHooks(QObject):
    """Connects the download and print handlers on the GUI thread.

    Attributes:
        install (pyqtSignal): Emitted from any thread to connect the handlers.
    """

    install = pyqtSignal()

    def __init__(self, window: webview.Window) -> None:
        """Creates the hooks for a shown window and moves them to its GUI thread.

        Args:
            window (webview.Window): The pywebview window, already shown.
        """
        super().__init__()
        self._main = window.native
        self._view = window.native.webview
        self._printer: QPrinter | None = None
        self.moveToThread(self._main.thread())
        self.install.connect(self._install)

    @pyqtSlot()
    def _install(self) -> None:
        """Connects the handlers to the page and its profile."""
        page = self._view.page()
        page.profile().downloadRequested.connect(self._download)
        page.printRequested.connect(self._print)

    def _download(self, download: QWebEngineDownloadRequest) -> None:
        """Asks where to save a download, starting from the name the page gave it.

        Args:
            download (QWebEngineDownloadRequest): The download the page started.
        """
        suggested = Path(download.downloadDirectory()) / download.downloadFileName()
        path, _ = QFileDialog.getSaveFileName(self._main, "", str(suggested))
        if not path:
            download.cancel()
            return
        download.setDownloadDirectory(str(Path(path).parent))
        download.setDownloadFileName(Path(path).name)
        download.accept()

    def _print(self) -> None:
        """Shows the system print dialog and prints the page, or saves it as PDF."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if QPrintDialog(printer, self._main).exec() != QDialog.DialogCode.Accepted:
            return
        self._printer = printer  # must live until the page is printed
        self._view.print(printer)


_hooks: list[WindowHooks] = []  # keeps the hooks alive with the window


def connect_hooks(window: webview.Window) -> None:
    """Connects the handlers once the window is shown; run by `webview.start` in a thread.

    Args:
        window (webview.Window): The pywebview window.
    """
    window.events.shown.wait()
    _hooks.append(WindowHooks(window))
    _hooks[-1].install.emit()
