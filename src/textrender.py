"""Render (possibly RTL / mixed) text to a transparent image using Qt's bidi-aware layout."""
import math

from PySide6.QtCore import Qt, QBuffer, QIODevice
from PySide6.QtGui import (QImage, QPainter, QColor, QFont, QTextDocument, QTextOption,
                           QTextCharFormat, QTextCursor)


def auto_direction_option() -> QTextOption:
    opt = QTextOption()
    opt.setTextDirection(Qt.LayoutDirection.LayoutDirectionAuto)
    return opt


def make_doc(text: str, size_px: float, color=(0, 0, 0), family="Arial", bold=False) -> QTextDocument:
    doc = QTextDocument()
    font = QFont(family)
    font.setPixelSize(max(1, int(round(size_px))))
    font.setBold(bold)
    doc.setDefaultFont(font)
    doc.setDefaultTextOption(auto_direction_option())
    doc.setDocumentMargin(size_px * 0.12)
    doc.setPlainText(text)
    cur = QTextCursor(doc)
    cur.select(QTextCursor.SelectionType.Document)
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(*[int(c) for c in color]))
    cur.mergeCharFormat(fmt)
    doc.setTextWidth(-1)
    doc.setTextWidth(math.ceil(doc.idealWidth()) + 1)
    return doc


def render_text(text: str, size_pt: float = 12, color=(0, 0, 0), family="Arial",
                bold=False, supersample: int = 4):
    """Return (QImage, width_pt, height_pt). Image is ARGB with transparent background."""
    size_pt = max(2.0, min(float(size_pt), 300.0))
    # A stamp wider than a page is useless, and one very long line makes Qt layout take minutes:
    # bound the line length by the font size, and the number of lines.
    max_line = max(4, int(1500 / (size_pt * 0.5)))
    text = "\n".join(ln[:max_line] for ln in text.split("\n")[:80])
    doc = make_doc(text, size_pt * supersample, color, family, bold)
    sz = doc.size()
    area = sz.width() * sz.height()
    if area > 6e6 and supersample > 1:            # huge text: lower the oversampling instead of making a 100 MB image
        supersample = max(1, int(supersample * math.sqrt(6e6 / area)))
        doc = make_doc(text, size_pt * supersample, color, family, bold)
        sz = doc.size()
    w, h = max(1, math.ceil(sz.width())), max(1, math.ceil(sz.height()))
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    doc.drawContents(p)
    p.end()
    return img, w / supersample, h / supersample


def image_to_png(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())
