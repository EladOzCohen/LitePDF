"""Signature library: draw with mouse/pen/touch or type a name in a handwriting font.

Signatures are saved as transparent PNGs in %APPDATA%\\LitePDF\\signatures and can be dropped
onto any document with one click.
"""
from __future__ import annotations

import math
import os
import time
from pathlib import Path

from PySide6.QtCore import Qt, QPointF, QRectF, QSize, Signal
from PySide6.QtGui import (QImage, QPainter, QPainterPath, QPen, QColor, QFontDatabase, QFont,
                           QPixmap)
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QPushButton,
                               QLineEdit, QListWidget, QListWidgetItem, QLabel, QButtonGroup,
                               QRadioButton, QSlider, QDialogButtonBox)

from i18n import T
from textrender import render_text, image_to_png

HANDWRITING_FONTS = ["Segoe Script", "Ink Free", "Lucida Handwriting", "Brush Script MT",
                     "Freestyle Script", "Mistral", "Gabriola", "Segoe Print", "Bradley Hand ITC",
                     "Kristen ITC", "Monotype Corsiva", "Arial"]
INK_COLORS = [("ink_black", (0.05, 0.05, 0.08)), ("ink_blue", (0.05, 0.12, 0.62))]


def available_fonts() -> list[str]:
    have = set(QFontDatabase.families())
    out = [f for f in HANDWRITING_FONTS if f in have]
    return out or ["Arial"]


def render_signature_text(name: str, family: str, color=(0.05, 0.12, 0.62), size_pt=48) -> QImage:
    img, _, _ = render_text(name, size_pt, tuple(int(c * 255) for c in color), family, supersample=3)
    return img


class SignatureStore:
    def __init__(self):
        base = os.environ.get("APPDATA") or str(Path.home())
        self.dir = Path(base) / "LitePDF" / "signatures"
        self.dir.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[Path]:
        return sorted(self.dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)

    def add_png(self, png: bytes) -> Path:
        p = self.dir / f"sig_{time.strftime('%Y%m%d_%H%M%S')}.png"
        p.write_bytes(png)
        return p

    def delete(self, path: Path):
        try:
            path.unlink()
        except OSError:
            pass


class DrawPad(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(560, 210)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.strokes: list[list[QPointF]] = []
        self.color = INK_COLORS[0][1]
        self.width = 3.2
        self._drawing = False

    def set_color(self, c):
        self.color = c
        self.update()

    def set_width(self, w: float):
        self.width = w
        self.update()

    def clear(self):
        self.strokes.clear()
        self.update()
        self.changed.emit()

    def is_empty(self) -> bool:
        return not self.strokes

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drawing = True
            self.strokes.append([ev.position()])
            self.update()

    def mouseMoveEvent(self, ev):
        if self._drawing and self.strokes:
            pts = self.strokes[-1]
            p = ev.position()
            if (p - pts[-1]).manhattanLength() >= 1.5:
                pts.append(p)
                self.update()

    def mouseReleaseEvent(self, ev):
        if self._drawing:
            self._drawing = False
            self.changed.emit()

    @staticmethod
    def _path(pts: list[QPointF]) -> QPainterPath:
        path = QPainterPath(pts[0])
        if len(pts) < 3:
            for p in pts[1:]:
                path.lineTo(p)
            return path
        for i in range(1, len(pts) - 1):
            mid = (pts[i] + pts[i + 1]) / 2
            path.quadTo(pts[i], mid)
        path.lineTo(pts[-1])
        return path

    def _paint_strokes(self, p: QPainter, scale=1.0):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor.fromRgbF(*self.color), self.width * scale, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        for pts in self.strokes:
            if len(pts) == 1:
                p.setBrush(QColor.fromRgbF(*self.color))
                r = self.width * scale / 2
                c = pts[0] * scale
                p.drawEllipse(c, r, r)
                p.setBrush(Qt.BrushStyle.NoBrush)
            else:
                p.save()
                p.scale(scale, scale)
                pen2 = QPen(pen)
                pen2.setWidthF(self.width)
                p.setPen(pen2)
                p.drawPath(self._path(pts))
                p.restore()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("white"))
        p.setPen(QPen(QColor("#cfd3d8"), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        base = int(self.height() * 0.72)
        p.setPen(QPen(QColor("#e0e3e8"), 1, Qt.PenStyle.DashLine))
        p.drawLine(20, base, self.width() - 20, base)
        p.setPen(QColor("#b8bcc2"))
        p.drawText(24, base + 18, "✕")
        if not self.strokes:
            p.setPen(QColor("#9aa0a6"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, T("draw_here"))
        self._paint_strokes(p)

    def image(self) -> QImage | None:
        if not self.strokes:
            return None
        pad = self.width * 2 + 4
        xs = [pt.x() for s in self.strokes for pt in s]
        ys = [pt.y() for s in self.strokes for pt in s]
        x0, x1 = max(0, min(xs) - pad), min(self.width_px(), max(xs) + pad)
        y0, y1 = max(0, min(ys) - pad), min(self.height(), max(ys) + pad)
        sc = 3.0
        img = QImage(max(2, math.ceil((x1 - x0) * sc)), max(2, math.ceil((y1 - y0) * sc)),
                     QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        p = QPainter(img)
        p.translate(-x0 * sc, -y0 * sc)
        self._paint_strokes(p, sc)
        p.end()
        return img

    def width_px(self) -> int:
        return super().width()


class TypePad(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(T("type_name"))
        self.edit.setStyleSheet("font-size:14pt;padding:4px;")
        self.edit.textChanged.connect(self._refresh)
        lay.addWidget(self.edit)
        self.fonts = QListWidget()
        self.fonts.setFixedHeight(150)
        self.fonts.setIconSize(QSize(1, 1))
        for f in available_fonts():
            it = QListWidgetItem(f)
            it.setData(Qt.ItemDataRole.UserRole, f)
            self.fonts.addItem(it)
        self.fonts.setCurrentRow(0)
        self.fonts.currentRowChanged.connect(self._refresh)
        lay.addWidget(self.fonts)
        self.preview = QLabel()
        self.preview.setFixedHeight(90)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background:white;border:1px solid #cfd3d8;")
        lay.addWidget(self.preview)
        self.color = INK_COLORS[0][1]

    def set_color(self, c):
        self.color = c
        self._refresh()

    def _family(self) -> str:
        it = self.fonts.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else "Arial"

    def _refresh(self, *_):
        for i in range(self.fonts.count()):
            it = self.fonts.item(i)
            f = QFont(it.data(Qt.ItemDataRole.UserRole))
            f.setPointSize(15)
            it.setFont(f)
            it.setText(self.edit.text().strip() or it.data(Qt.ItemDataRole.UserRole))
        img = self.image()
        if img is None:
            self.preview.clear()
        else:
            pm = QPixmap.fromImage(img.scaledToHeight(70, Qt.TransformationMode.SmoothTransformation))
            self.preview.setPixmap(pm)
        self.changed.emit()

    def image(self) -> QImage | None:
        name = self.edit.text().strip()
        if not name:
            return None
        return render_signature_text(name, self._family(), self.color)


class SignatureDialog(QDialog):
    """Create a new signature. After accept(), .png holds the PNG bytes."""

    def __init__(self, parent=None, name_hint=""):
        super().__init__(parent)
        self.setWindowTitle(T("new_signature"))
        self.png: bytes | None = None
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.pad = DrawPad()
        self.typepad = TypePad()
        if name_hint:
            self.typepad.edit.setText(name_hint)
        draw_page = QWidget()
        dl = QVBoxLayout(draw_page)
        dl.addWidget(self.pad, 0, Qt.AlignmentFlag.AlignCenter)
        row = QHBoxLayout()
        clear = QPushButton(T("clear"))
        clear.clicked.connect(self.pad.clear)
        row.addWidget(clear)
        row.addStretch(1)
        row.addWidget(QLabel(T("thickness")))
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(15, 70)
        sl.setValue(32)
        sl.setFixedWidth(120)
        sl.valueChanged.connect(lambda v: self.pad.set_width(v / 10))
        row.addWidget(sl)
        dl.addLayout(row)
        self.tabs.addTab(draw_page, T("tab_draw"))
        self.tabs.addTab(self.typepad, T("tab_type"))
        lay.addWidget(self.tabs)

        crow = QHBoxLayout()
        crow.addWidget(QLabel(T("ink")))
        self.group = QButtonGroup(self)
        for i, (key, col) in enumerate(INK_COLORS):
            rb = QRadioButton(T(key))
            rb.setChecked(i == 0)
            rb.toggled.connect(lambda on, c=col: on and self._set_color(c))
            self.group.addButton(rb)
            crow.addWidget(rb)
        crow.addStretch(1)
        lay.addLayout(crow)

        bb = QDialogButtonBox()
        self.ok = bb.addButton(T("save_signature"), QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton(T("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.tabs.currentChanged.connect(lambda _: self._update_ok())
        self.pad.changed.connect(self._update_ok)
        self.typepad.changed.connect(self._update_ok)
        self._update_ok()

    def _set_color(self, c):
        self.pad.set_color(c)
        self.typepad.set_color(c)

    def _current_image(self) -> QImage | None:
        return self.pad.image() if self.tabs.currentIndex() == 0 else self.typepad.image()

    def _update_ok(self):
        self.ok.setEnabled(self._current_image() is not None)

    def _accept(self):
        img = self._current_image()
        if img is None:
            return
        self.png = image_to_png(img)
        self.accept()
