"""Printing for pywebview's macOS window (WKWebView).

WebKit lays a printed page out at 125% of the paper's width and shrinks it to fit, so CSS
millimetres print 6.7% too large: a CSS pixel prints as 1 pt / 1.25 = 0.8 pt, not 0.75 pt. The
A4 Scoresheet (web/css/pages.css) came out about 294 mm high and spilled onto a second page.
This print scales by the inverse, so a millimetre prints as one, and keeps the system print
panel. The margins are the page's own (`@page`), which WebKit applies itself.
"""

import AppKit
import Foundation
from webview.platforms.cocoa import BrowserView

# A CSS px is 0.75 pt; WebKit prints it as 0.8 pt (measured on the CI runners' PDFs).
TRUE_SIZE = 0.75 * 1.25


def print_info() -> AppKit.NSPrintInfo:
    """Builds the page setup: the user's paper, the page's width fitted, true size.

    Returns:
        AppKit.NSPrintInfo: A copy of the shared print info, set up for the page.
    """
    info = AppKit.NSPrintInfo.sharedPrintInfo().copy()
    info.setHorizontalPagination_(AppKit.NSFitPagination)
    info.setHorizontallyCentered_(False)
    info.setVerticallyCentered_(False)
    info.setScalingFactor_(TRUE_SIZE)
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
