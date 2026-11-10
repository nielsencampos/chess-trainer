"""Printing for pywebview's macOS window (WKWebView).

WKWebView ignores the page's CSS `@page` margins and pywebview prints with the printer's
printable area instead, which can leave the A4 Scoresheet a millimetre short of room and push
its signatures to a second page. This print uses the Scoresheet's own 10 mm margins, as
Chromium does on Linux and Windows, and keeps the system print panel.
"""

import AppKit
import Foundation
from webview.platforms.cocoa import BrowserView

# The Scoresheet's `@page { margin: 10mm }` (web/css/pages.css), in points.
MARGIN_PT = 10 / 25.4 * 72


def print_info() -> AppKit.NSPrintInfo:
    """Builds the page setup: the user's paper, the page's width fitted, 10 mm margins.

    Returns:
        AppKit.NSPrintInfo: A copy of the shared print info, set up for the page.
    """
    info = AppKit.NSPrintInfo.sharedPrintInfo().copy()
    info.setHorizontalPagination_(AppKit.NSFitPagination)
    info.setHorizontallyCentered_(False)
    info.setVerticallyCentered_(False)
    for set_margin in (
        info.setTopMargin_,
        info.setBottomMargin_,
        info.setLeftMargin_,
        info.setRightMargin_,
    ):
        set_margin(MARGIN_PT)
    return info


def print_operation(web_view: object, info: AppKit.NSPrintInfo) -> AppKit.NSPrintOperation:
    """Makes the web view's print operation for a page setup.

    Args:
        web_view (object): The WKWebView.
        info (AppKit.NSPrintInfo): The page setup.

    Returns:
        AppKit.NSPrintOperation: The operation, not yet run.
    """
    operation = web_view.printOperationWithPrintInfo_(info)
    # A WKWebView print operation lays out nothing in a view without a frame.
    size = info.paperSize()
    operation.view().setFrame_(Foundation.NSMakeRect(0, 0, size.width, size.height))
    return operation


def print_webview(web_view: object) -> None:
    """Shows the system print panel for the page, as a sheet on its window.

    Args:
        web_view (object): The WKWebView.
    """
    print_operation(
        web_view, print_info()
    ).runOperationModalForWindow_delegate_didRunSelector_contextInfo_(
        web_view.window(), None, None, None
    )


def install() -> None:
    """Replaces pywebview's print with this one; call it before `webview.start`."""
    BrowserView.print_webview = staticmethod(print_webview)
