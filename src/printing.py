"""Printing: render pages with PyMuPDF (annotations included) and send them through Qt's printer."""
from __future__ import annotations

import pymupdf
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QImage, QPainter, QTransform
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QAbstractPrintDialog
from PySide6.QtWidgets import QProgressDialog, QApplication, QMessageBox

from i18n import T

MAX_DPI = 300


def _page_numbers(printer: QPrinter, total: int, current: int) -> list[int]:
    rng = printer.printRange()
    if rng == QPrinter.PrintRange.CurrentPage:
        return [current]
    if rng == QPrinter.PrintRange.PageRange:
        a = max(1, printer.fromPage())
        b = min(total, printer.toPage() or total)
        return list(range(a - 1, b))
    return list(range(total))


def print_document(parent, doc: pymupdf.Document, current_page: int = 0) -> bool:
    """Show the print dialog and print. Returns True if something was sent to the printer."""
    total = doc.page_count
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setFullPage(False)
    dlg = QPrintDialog(printer, parent)
    dlg.setOption(QAbstractPrintDialog.PrintDialogOption.PrintPageRange, True)
    dlg.setOption(QAbstractPrintDialog.PrintDialogOption.PrintCurrentPage, True)
    dlg.setOption(QAbstractPrintDialog.PrintDialogOption.PrintCollateCopies, True)
    dlg.setMinMax(1, total)
    dlg.setWindowTitle(T("print"))
    if dlg.exec() != QPrintDialog.DialogCode.Accepted:
        return False

    pages = _page_numbers(printer, total, current_page)
    if not pages:
        return False
    dpi = min(int(printer.resolution() or 300), MAX_DPI)
    progress = QProgressDialog(T("printing"), T("cancel"), 0, len(pages), parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(400)

    painter = QPainter()
    if not painter.begin(printer):
        QMessageBox.warning(parent, T("print"), T("print_failed"))
        return False
    try:
        for n, pno in enumerate(pages):
            if progress.wasCanceled():
                break
            progress.setValue(n)
            QApplication.processEvents()
            if n > 0:
                printer.newPage()
            _draw_page(painter, printer, doc[pno], dpi)
    finally:
        painter.end()
        progress.setValue(len(pages))
    return True


def _draw_page(painter: QPainter, printer: QPrinter, page: pymupdf.Page, dpi: int):
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    img = QImage(bytes(pix.samples), pix.width, pix.height, pix.stride,
                 QImage.Format.Format_RGB888)
    target = printer.pageRect(QPrinter.Unit.DevicePixel)     # printable area in device pixels
    # Auto-rotate landscape pages onto portrait paper (and vice versa).
    img_landscape = img.width() > img.height()
    paper_landscape = target.width() > target.height()
    if img_landscape != paper_landscape:
        img = img.transformed(QTransform().rotate(90), Qt.TransformationMode.SmoothTransformation)
    # Physical size at 100 %, shrunk only if it does not fit.
    dev_dpi = printer.resolution() or dpi
    actual_w = img.width() * dev_dpi / dpi
    actual_h = img.height() * dev_dpi / dpi
    scale = min(1.0, target.width() / actual_w, target.height() / actual_h)
    w, h = actual_w * scale, actual_h * scale
    x = target.x() + (target.width() - w) / 2
    y = target.y() + (target.height() - h) / 2
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawImage(QRectF(x, y, w, h), img)
