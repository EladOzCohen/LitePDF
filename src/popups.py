"""Floating editors shown over the page: sticky-note editor and free-text input.

Both use per-paragraph automatic text direction so Hebrew (RTL) and English (LTR)
paragraphs each align and flow correctly, even when mixed.
"""
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QTextEdit, QToolButton,
                               QLabel, QSizeGrip, QWidget)

import icons
from i18n import T
from textrender import auto_direction_option


class AutoDirEdit(QTextEdit):
    """QTextEdit whose paragraphs pick their direction from their first strong character."""
    submit = Signal()
    escaped = Signal()

    def __init__(self, enter_submits=False, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.document().setDefaultTextOption(auto_direction_option())
        self._enter_submits = enter_submits
        self.setFrameShape(QFrame.Shape.NoFrame)

    def keyPressEvent(self, ev):
        k = ev.key()
        mods = ev.modifiers()
        if k == Qt.Key.Key_Escape:
            self.escaped.emit()
            return
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
            shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
            if ctrl or (self._enter_submits and not shift):
                self.submit.emit()
                return
        super().keyPressEvent(ev)


class NotePopup(QFrame):
    """Sticky-note editor. Emits committed(text) once when closed; deleteRequested on trash."""
    committed = Signal(str)
    deleteRequested = Signal()

    def __init__(self, parent, text="", title="", deletable=True, delete_tip=None):
        super().__init__(parent)
        self.setObjectName("NotePopup")
        self._done = False
        self.setStyleSheet(
            "#NotePopup{background:#fff7b0;border:1px solid #c9b200;border-radius:6px;}"
            "QTextEdit{background:transparent;color:#1d1d1d;selection-background-color:#ffd54a;"
            "selection-color:#000;}"
            "QLabel{color:#6b5d00;}"
            "QToolButton{border:none;border-radius:4px;padding:3px;background:transparent;}"
            "QToolButton:hover{background:#f1de62;}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 6, 4)
        lay.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(2)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-size:9pt;")
        head.addWidget(self.title, 1)
        if deletable:
            self.btn_del = QToolButton()
            self.btn_del.setIcon(icons.icon("trash", "#6b5d00"))
            self.btn_del.setToolTip(delete_tip or T("delete"))
            self.btn_del.clicked.connect(self._on_delete)
            head.addWidget(self.btn_del)
        self.btn_ok = QToolButton()
        self.btn_ok.setIcon(icons.icon("check", "#6b5d00"))
        self.btn_ok.setToolTip(T("done") + "  (Ctrl+Enter)")
        self.btn_ok.clicked.connect(lambda: self.finish())
        head.addWidget(self.btn_ok)
        lay.addLayout(head)

        self.edit = AutoDirEdit()
        f = QFont("Segoe UI")
        f.setPointSizeF(11)
        self.edit.setFont(f)
        self.edit.setPlaceholderText(T("note_placeholder"))
        self.edit.setPlainText(text)
        self.edit.submit.connect(lambda: self.finish())
        self.edit.escaped.connect(lambda: self.finish())
        lay.addWidget(self.edit, 1)

        grip_row = QHBoxLayout()
        grip_row.addStretch(1)
        grip_row.addWidget(QSizeGrip(self))
        lay.addLayout(grip_row)
        self.resize(300, 170)
        self.setMinimumSize(200, 110)

    def text(self) -> str:
        return self.edit.toPlainText()

    def focus_end(self):
        self.edit.setFocus()
        c = self.edit.textCursor()
        c.movePosition(c.MoveOperation.End)
        self.edit.setTextCursor(c)

    def _on_delete(self):
        if self._done:
            return
        self._done = True
        self.deleteRequested.emit()
        self.hide()
        self.deleteLater()

    def finish(self):
        if self._done:
            return
        self._done = True
        t = self.text()
        self.committed.emit(t)
        self.hide()
        self.deleteLater()


class TextPopup(QFrame):
    """Inline text input for the 'type on page' tool. Looks like the final text."""
    committed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent, text, px_size, color, family="Arial"):
        super().__init__(parent)
        self._done = False
        self.setObjectName("TextPopup")
        c = QColor(*[int(v) for v in color])
        self.setStyleSheet(
            "#TextPopup{background:rgba(255,255,255,235);border:1px dashed #3d7eff;}"
            f"QTextEdit{{background:transparent;color:{c.name()};}}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        self.edit = AutoDirEdit(enter_submits=True)
        f = QFont(family)
        f.setPixelSize(max(6, int(px_size)))
        self.edit.setFont(f)
        self.edit.document().setDocumentMargin(max(1, px_size * 0.12))
        self.edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.edit.setPlainText(text)
        self.edit.submit.connect(self.finish)
        self.edit.escaped.connect(self.cancel)
        self.edit.textChanged.connect(self._autosize)
        lay.addWidget(self.edit)
        self.hint = QLabel(T("text_hint"))
        self.hint.setStyleSheet("font-size:8pt;color:#3d7eff;background:transparent;")
        lay.addWidget(self.hint)
        self._autosize()

    def _autosize(self):
        d = self.edit.document()
        d.setTextWidth(-1)
        w = int(d.idealWidth()) + 14
        h = int(d.size().height()) + 4
        w = max(w, 90)
        self.edit.setFixedSize(w, h)
        self.adjustSize()

    def text(self) -> str:
        return self.edit.toPlainText()

    def focus(self):
        self.edit.setFocus()
        c = self.edit.textCursor()
        c.movePosition(c.MoveOperation.End)
        self.edit.setTextCursor(c)

    def finish(self):
        if self._done:
            return
        self._done = True
        self.committed.emit(self.text())
        self.hide()
        self.deleteLater()

    def cancel(self):
        if self._done:
            return
        self._done = True
        self.cancelled.emit()
        self.hide()
        self.deleteLater()
