"""Item delegates that give each list entry its own text direction (Hebrew / English per item)."""
import unicodedata

from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import QTextDocument, QPalette, QAbstractTextDocumentLayout, QFont
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem

from textrender import auto_direction_option

HEAD_ROLE = Qt.ItemDataRole.UserRole + 1


def is_rtl_text(s: str) -> bool:
    for ch in s:
        d = unicodedata.bidirectional(ch)
        if d in ("R", "AL"):
            return True
        if d == "L":
            return False
    return False


class AutoDirDelegate(QStyledItemDelegate):
    """Single/multi-line text whose direction follows its first strong character."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.direction = (Qt.LayoutDirection.RightToLeft if is_rtl_text(option.text)
                            else Qt.LayoutDirection.LeftToRight)


class NoteDelegate(QStyledItemDelegate):
    """Two-part item: small page label on top, wrapped note text below (auto direction)."""
    PAD = 8

    def _doc(self, text: str, width: int, font: QFont) -> QTextDocument:
        doc = QTextDocument()
        doc.setDefaultFont(font)
        doc.setDefaultTextOption(auto_direction_option())
        doc.setDocumentMargin(0)
        doc.setPlainText(text)
        doc.setTextWidth(max(40, width))
        return doc

    def sizeHint(self, option, index):
        w = option.rect.width()
        if w <= 0 and option.widget is not None:
            w = option.widget.viewport().width()
        fm = option.fontMetrics
        doc = self._doc(index.data(Qt.ItemDataRole.DisplayRole) or "", w - 2 * self.PAD, option.font)
        return QSize(w, fm.height() + int(doc.size().height()) + 2 * self.PAD + 4)

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else None
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        role = QPalette.ColorRole.HighlightedText if selected else QPalette.ColorRole.Text
        color = opt.palette.color(QPalette.ColorGroup.Active, role)
        fm = opt.fontMetrics
        r = opt.rect
        painter.save()
        head = index.data(HEAD_ROLE) or ""
        hc = color
        hc.setAlpha(150)
        painter.setPen(hc)
        painter.drawText(QRect(r.left() + self.PAD, r.top() + self.PAD // 2, r.width() - 2 * self.PAD, fm.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, head)
        doc = self._doc(index.data(Qt.ItemDataRole.DisplayRole) or "", r.width() - 2 * self.PAD, opt.font)
        painter.translate(r.left() + self.PAD, r.top() + self.PAD // 2 + fm.height() + 3)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.palette.setColor(QPalette.ColorRole.Text, color)
        doc.documentLayout().draw(painter, ctx)
        painter.restore()
