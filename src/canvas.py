"""PdfCanvas: lazy-rendering PDF view with text selection, markup, notes, text and signature stamps.

Design notes
------------
* Everything the user adds is a *standard PDF annotation* (Highlight / Underline / StrikeOut /
  Text(sticky note) / Stamp), so it shows up in other readers too.
* Typed text and signatures are rendered to transparent PNGs and stored as image Stamp
  annotations (this is what makes Hebrew / RTL text look right everywhere). For text stamps
  the original string is kept in the annotation's /Contents so it can be edited again here.
* Deleting is "soft" (annotation gets the Hidden flag) so undo/redo is trivial. Hidden ones are
  really removed from the file when saving (purge_trashed()).
"""
from __future__ import annotations

import bisect
import math
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass, field

import pymupdf
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, QPointF, QTimer, Signal, QUrl, QElapsedTimer
from PySide6.QtGui import (QPainter, QColor, QImage, QPixmap, QPen, QBrush, QCursor,
                           QDesktopServices, QAction, QKeyEvent)
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QMenu, QFrame

from i18n import T
from popups import NotePopup, TextPopup
from textrender import render_text, image_to_png

K = 96.0 / 72.0          # px per pt at 100 %
MARGIN, GAP, HS = 14, 12, 9
HIDDEN = pymupdf.PDF_ANNOT_IS_HIDDEN

A_TEXT = pymupdf.PDF_ANNOT_TEXT
A_STAMP = pymupdf.PDF_ANNOT_STAMP
A_HL = pymupdf.PDF_ANNOT_HIGHLIGHT
A_UL = pymupdf.PDF_ANNOT_UNDERLINE
A_ST = pymupdf.PDF_ANNOT_STRIKE_OUT
A_SQ = pymupdf.PDF_ANNOT_SQUIGGLY
A_POPUP = pymupdf.PDF_ANNOT_POPUP
MARKUP = {A_HL, A_UL, A_ST, A_SQ}
MARKUP_TOOLS = {"highlight", "underline", "strike"}

HL_COLORS = [
    ("yellow", (1.0, 0.92, 0.15)),
    ("green", (0.45, 0.95, 0.45)),
    ("pink", (1.0, 0.55, 0.8)),
    ("blue", (0.5, 0.8, 1.0)),
    ("orange", (1.0, 0.7, 0.3)),
]
TEXT_STAMP_TAG = "litepdf-text"


def _bidi_counts(text: str) -> tuple[int, int]:
    r = l = 0
    for ch in text:
        d = unicodedata.bidirectional(ch)
        if d in ("R", "AL"):
            r += 1
        elif d == "L":
            l += 1
    return r, l


def row_is_rtl(words) -> bool:
    r = l = 0
    for w in words:
        a, b = _bidi_counts(w[4])
        r += a
        l += b
    return r > l


def fix_rtl_row(words: list) -> list:
    """words are ordered right-to-left; restore left-to-right order inside runs of Latin words."""
    out, run = [], []
    for w in words:
        if _bidi_counts(w[4])[1] > 0 and _bidi_counts(w[4])[0] == 0:
            run.append(w)
        else:
            out.extend(reversed(run))
            run = []
            out.append(w)
    out.extend(reversed(run))
    return out


def _stream_is_scrambled(raw: list) -> bool:
    """True when the text stream jumps around the page (so block order can't be trusted).

    A normal single/multi-column document only jumps upwards a few times (new column / new
    block). Scrambled streams jump up constantly."""
    if len(raw) < 12:
        return False
    jumps = 0
    for a, b in zip(raw, raw[1:]):
        ha = max(a[3] - a[1], 1.0)
        if (b[1] + b[3]) / 2 < (a[1] + a[3]) / 2 - 0.6 * ha:
            jumps += 1
    return jumps > 3 and jumps > 0.06 * len(raw)


def reading_order(raw: list) -> list:
    """Re-order PyMuPDF 'words' by how the page LOOKS, not by internal stream order.

    Many PDFs (Word exports, Hebrew documents, scans with OCR) store text in a scrambled or
    visual order, so selecting by stream index picks the wrong words. Here: blocks keep their
    stream order (so columns stay separate), lines inside a block are found geometrically
    (top to bottom) and words inside a line go left-to-right, or right-to-left for RTL lines.
    The 7th field becomes the row number (used to detect line breaks).
    """
    blocks: dict = {}
    scrambled = _stream_is_scrambled(raw)
    for w in raw:
        blocks.setdefault(0 if scrambled else w[5], []).append(w)
    out = []
    for bno, ws in blocks.items():
        ws = sorted(ws, key=lambda w: (w[1] + w[3]) / 2)
        rows: list = []
        for w in ws:
            h = w[3] - w[1]
            if rows:
                r = rows[-1]
                overlap = min(w[3], r[1]) - max(w[1], r[0])
                if overlap > 0.5 * min(h, r[1] - r[0]):
                    r[2].append(w)
                    r[0], r[1] = min(r[0], w[1]), max(r[1], w[3])
                    continue
            rows.append([w[1], w[3], [w]])
        for ri, (_, _, rw) in enumerate(rows):
            rw.sort(key=lambda w: (w[0] + w[2]) / 2, reverse=row_is_rtl(rw))
            for w in rw:
                out.append((w[0], w[1], w[2], w[3], w[4], bno, ri, w[7]))
    return out


@dataclass
class AInfo:
    xref: int
    kind: int
    rect: pymupdf.Rect
    quads: list = field(default_factory=list)
    content: str = ""
    subject: str = ""


@dataclass
class Cmd:
    undo: object
    redo: object
    pages: list


def qimage_from_pix(pix: pymupdf.Pixmap, fmt) -> QImage:
    return QImage(bytes(pix.samples), pix.width, pix.height, pix.stride, fmt).copy()


class PdfCanvas(QAbstractScrollArea):
    pageChanged = Signal(int)
    zoomChanged = Signal(float)
    dirtyChanged = Signal(bool)
    selectionChanged = Signal(bool)
    undoStateChanged = Signal()
    requestToolReset = Signal()
    statusMessage = Signal(str)
    annotsChanged = Signal()
    searchResult = Signal(int, int)
    toolShortcut = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.viewport().setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.doc: pymupdf.Document | None = None
        self.path: str | None = None
        self.zoom = 1.0
        self.fit_mode: str | None = "width"      # 'width' | 'page' | None
        self.invert = False
        self.dark_bg = False
        self.author = ""

        self.page_rects: list[pymupdf.Rect] = []
        self.tops: list[int] = []
        self.pw: list[int] = []
        self.ph: list[int] = []
        self.content_h = 0
        self.content_w = 0
        self._cur_page = 0

        self._page_objs: dict = {}
        self._cache: OrderedDict = OrderedDict()
        self._cache_bytes = 0
        self._words: dict[int, list] = {}
        self._annots: dict[int, list[AInfo]] = {}
        self._links: dict[int, list] = {}

        # tools
        self.tool = "select"
        self.hl_color = HL_COLORS[0][1]
        self.text_opts = {"size": 12.0, "color": (0, 0, 0), "family": "Arial"}
        self.text_preset: str | None = None
        self.pending_png: bytes | None = None
        self.pending_img: QImage | None = None
        self.pending_w_pt = 150.0

        # selection state
        self.sel_words: tuple | None = None     # (page, i0, i1)
        self.sel_annot: tuple | None = None     # (page, xref)
        self._drag: dict | None = None
        self._press_pos = QPoint()
        self._moved = False
        self._pending_click: dict | None = None
        self._hover: QPoint | None = None

        # undo / trash
        self.undo_stack: list[Cmd] = []
        self.redo_stack: list[Cmd] = []
        self.trashed: set[tuple[int, int]] = set()
        self._dirty = False

        # popups
        self._popup = None
        self._popup_anchor: tuple | None = None

        # search
        self._search_text = ""
        self._hits: list[tuple[int, pymupdf.Rect]] = []
        self._hits_by_page: dict[int, list] = {}
        self._hit_idx = -1

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(self._on_scroll)
        self._prefetch_timer = QTimer(self)
        self._prefetch_timer.setSingleShot(True)
        self._prefetch_timer.timeout.connect(self._prefetch)
        self._anim_timer = QTimer(self)
        self._anim_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._anim_timer.timeout.connect(self._anim_step)
        self._anim_clock = QElapsedTimer()
        self._anim_pos = 0.0
        self._anim_target = 0.0
        self._anim_setting = False
        self._last_scroll_v = 0
        self._scroll_dir = 1

    # ------------------------------------------------------------------ document
    @property
    def s(self) -> float:
        return self.zoom * K

    @property
    def page_count(self) -> int:
        return self.doc.page_count if self.doc else 0

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def set_document(self, doc: pymupdf.Document | None, path: str | None):
        self._close_popup(commit=False)
        self.doc, self.path = doc, path
        self._cache.clear()
        self._cache_bytes = 0
        self._words.clear()
        self._annots.clear()
        self._links.clear()
        self.sel_words = None
        self.sel_annot = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.trashed.clear()
        self._drag = None
        self.clear_search()
        self._set_dirty(False)
        self.undoStateChanged.emit()
        self._compute_page_rects()
        self._cur_page = 0
        if doc:
            self._apply_fit()
        self._relayout()
        self.viewport().update()

    def _page(self, i: int):
        """Cached Page object. Annot objects only stay valid while their Page is alive."""
        p = self._page_objs.get(i)
        if p is None:
            p = self.doc[i]
            self._page_objs[i] = p
            if len(self._page_objs) > 12:
                for k in list(self._page_objs)[:4]:
                    if k != i:
                        del self._page_objs[k]
        return p

    def _compute_page_rects(self):
        self._page_objs.clear()
        self.page_rects = [self.doc[i].rect for i in range(self.doc.page_count)] if self.doc else []

    def _set_dirty(self, v: bool):
        if v != self._dirty:
            self._dirty = v
            self.dirtyChanged.emit(v)

    def mark_clean(self):
        self._set_dirty(False)

    # ------------------------------------------------------------------ layout / zoom
    def _relayout(self):
        if not self.doc:
            self.tops, self.pw, self.ph = [], [], []
            self.content_h = self.content_w = 0
            self.verticalScrollBar().setRange(0, 0)
            self.horizontalScrollBar().setRange(0, 0)
            return
        s = self.s
        self.pw = [max(1, int(round(r.width * s))) for r in self.page_rects]
        self.ph = [max(1, int(round(r.height * s))) for r in self.page_rects]
        y = MARGIN
        self.tops = []
        for h in self.ph:
            self.tops.append(y)
            y += h + GAP
        self.content_h = y - GAP + MARGIN
        self.content_w = (max(self.pw) if self.pw else 0) + 2 * MARGIN
        vp = self.viewport()
        vb, hb = self.verticalScrollBar(), self.horizontalScrollBar()
        vb.setRange(0, max(0, self.content_h - vp.height()))
        vb.setPageStep(max(1, vp.height()))
        vb.setSingleStep(48)
        hb.setRange(0, max(0, self.content_w - vp.width()))
        hb.setPageStep(max(1, vp.width()))
        hb.setSingleStep(48)

    def _apply_fit(self):
        if not self.doc or not self.fit_mode or not self.page_rects:
            return
        vp = self.viewport()
        maxw = max(r.width for r in self.page_rects)
        if self.fit_mode == "width":
            z = (vp.width() - 2 * MARGIN) / (maxw * K)
        else:
            r = self.page_rects[min(self._cur_page, len(self.page_rects) - 1)]
            z = min((vp.width() - 2 * MARGIN) / (r.width * K),
                    (vp.height() - 2 * MARGIN) / (r.height * K))
        self.zoom = max(0.1, min(8.0, z))

    def set_zoom(self, z: float, mode: str | None = None, anchor: QPoint | None = None):
        if not self.doc:
            return
        z = max(0.1, min(8.0, z))
        vp = self.viewport()
        vb, hb = self.verticalScrollBar(), self.horizontalScrollBar()
        if anchor is None:
            anchor = QPoint(vp.width() // 2, vp.height() // 2)
        cw_old = max(self.content_w, vp.width())
        fy = (vb.value() + anchor.y()) / max(1, self.content_h)
        fx = (hb.value() + anchor.x()) / max(1, cw_old)
        page_before = self._cur_page
        self.zoom, self.fit_mode = z, mode
        if mode:
            self._apply_fit()
        self._relayout()
        cw = max(self.content_w, vp.width())
        if mode == "page":
            self.goto_page(page_before)
        else:
            vb.setValue(int(fy * self.content_h - anchor.y()))
            hb.setValue(int(fx * cw - anchor.x()))
        self._cache_trim_scale()
        self._reposition_popup()
        self.zoomChanged.emit(self.zoom)
        self.viewport().update()

    def fit_width(self):
        self.set_zoom(self.zoom, "width")

    def fit_page(self):
        self.set_zoom(self.zoom, "page")

    def zoom_by(self, factor: float, anchor: QPoint | None = None):
        self.set_zoom(self.zoom * factor, None, anchor)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self.doc:
            if self.fit_mode:
                self._apply_fit()
                self.zoomChanged.emit(self.zoom)
            self._relayout()
            self._reposition_popup()

    def goto_page(self, n: int, y_pt: float = 0.0):
        if not self.doc:
            return
        n = max(0, min(self.page_count - 1, n))
        self.verticalScrollBar().setValue(int(self.tops[n] + y_pt * self.s - 8))
        self._on_scroll()

    # ---- smooth scrolling -------------------------------------------------
    def smooth_scroll_by(self, dy: float):
        """Glide the view by dy pixels (exponential ease-out; repeated calls accumulate)."""
        vb = self.verticalScrollBar()
        if not self._anim_timer.isActive():
            self._anim_pos = float(vb.value())
            self._anim_target = self._anim_pos
            self._anim_clock.start()
            self._anim_timer.start(8)
        self._anim_target = max(float(vb.minimum()), min(float(vb.maximum()), self._anim_target + dy))

    def _stop_anim(self):
        self._anim_timer.stop()

    def _anim_step(self):
        vb = self.verticalScrollBar()
        dt = min(20, max(1, self._anim_clock.restart()))   # cap: a slow frame must not cause a jump
        diff = self._anim_target - self._anim_pos
        if abs(diff) < 0.4:
            self._anim_pos = self._anim_target
            self._anim_timer.stop()
        else:
            self._anim_pos += diff * (1.0 - math.exp(-dt / 55.0))
        self._anim_setting = True
        vb.setValue(int(round(self._anim_pos)))
        self._anim_setting = False

    def _on_scroll(self, *_):
        if not self.doc:
            return
        if not self._anim_setting and self._anim_timer.isActive():
            self._stop_anim()                      # user dragged the scrollbar etc.
        v = self.verticalScrollBar().value()
        if v != self._last_scroll_v:
            self._scroll_dir = 1 if v > self._last_scroll_v else -1
            self._last_scroll_v = v
        y = self.verticalScrollBar().value() + self.viewport().height() // 3
        k = max(0, min(len(self.tops) - 1, bisect.bisect_right(self.tops, y) - 1))
        if k != self._cur_page:
            self._cur_page = k
            self.pageChanged.emit(k)
        self._reposition_popup()
        self.viewport().update()

    @property
    def current_page(self) -> int:
        return self._cur_page

    # ------------------------------------------------------------------ coordinate helpers
    def _origin(self, i: int) -> tuple[int, int]:
        vw = self.viewport().width()
        cw = max(self.content_w, vw)
        x = (cw - self.pw[i]) // 2 - self.horizontalScrollBar().value()
        y = self.tops[i] - self.verticalScrollBar().value()
        return x, y

    def _to_page(self, i: int, pos) -> tuple[float, float]:
        ox, oy = self._origin(i)
        return (pos.x() - ox) / self.s, (pos.y() - oy) / self.s

    def _to_px(self, i: int, x: float, y: float) -> QPointF:
        ox, oy = self._origin(i)
        return QPointF(ox + x * self.s, oy + y * self.s)

    def _rect_px(self, i: int, r) -> QRectF:
        ox, oy = self._origin(i)
        s = self.s
        return QRectF(ox + r.x0 * s, oy + r.y0 * s, (r.x1 - r.x0) * s, (r.y1 - r.y0) * s)

    def _page_at(self, pos, clamp=False) -> int:
        if not self.doc or not self.tops:
            return -1
        yc = pos.y() + self.verticalScrollBar().value()
        k = bisect.bisect_right(self.tops, yc) - 1
        if k < 0:
            return 0 if clamp else -1
        if yc <= self.tops[k] + self.ph[k]:
            ox, _ = self._origin(k)
            if clamp or ox <= pos.x() <= ox + self.pw[k]:
                return k
            return -1
        return k if clamp else -1

    def _visible_range(self) -> tuple[int, int]:
        vb = self.verticalScrollBar().value()
        vh = self.viewport().height()
        first = max(0, bisect.bisect_right(self.tops, vb) - 1)
        last = max(0, bisect.bisect_right(self.tops, vb + vh) - 1)
        return first, min(last, len(self.tops) - 1)

    # ------------------------------------------------------------------ rendering cache
    def _render_scale(self, i: int) -> float:
        rs = self.s * self.devicePixelRatioF()
        r = self.page_rects[i]
        area = r.width * r.height * rs * rs
        if area > 6e7:
            rs *= math.sqrt(6e7 / area)
        return rs

    def _pixmap(self, i: int) -> QPixmap:
        rs = self._render_scale(i)
        key = (i, round(rs, 3), self.invert)
        pm = self._cache.get(key)
        if pm is not None:
            self._cache.move_to_end(key)
            return pm
        pix = self._page(i).get_pixmap(matrix=pymupdf.Matrix(rs, rs), alpha=False)
        img = qimage_from_pix(pix, QImage.Format.Format_RGB888)
        if self.invert:
            img.invertPixels()
        pm = QPixmap.fromImage(img)
        self._cache[key] = pm
        self._cache_bytes += pm.width() * pm.height() * 4
        while len(self._cache) > 3 and (len(self._cache) > 16 or self._cache_bytes > 500e6):
            _, old = self._cache.popitem(last=False)
            self._cache_bytes -= old.width() * old.height() * 4
        return pm

    def _cache_trim_scale(self):
        keep = {}
        for k, pm in self._cache.items():
            if self.doc and k[0] < len(self.page_rects) and k[1] == round(self._render_scale(k[0]), 3):
                keep[k] = pm
        self._cache = OrderedDict(keep)
        self._cache_bytes = sum(p.width() * p.height() * 4 for p in self._cache.values())

    def _invalidate(self, pages):
        for i in pages:
            for k in [k for k in self._cache if k[0] == i]:
                pm = self._cache.pop(k)
                self._cache_bytes -= pm.width() * pm.height() * 4
            self._annots.pop(i, None)
        self.viewport().update()
        self.annotsChanged.emit()

    def set_invert(self, v: bool):
        if v != self.invert:
            self.invert = v
            self._cache.clear()
            self._cache_bytes = 0
            self.viewport().update()

    def _prefetch(self):
        if not self.doc:
            return
        first, last = self._visible_range()
        if self._scroll_dir >= 0:
            order = (last + 1, last + 2, first - 1)
        else:
            order = (first - 1, first - 2, last + 1)
        for i in order:
            if 0 <= i < self.page_count:
                key = (i, round(self._render_scale(i), 3), self.invert)
                if key not in self._cache:
                    self._pixmap(i)
                    self._prefetch_timer.start(10)
                    return

    # ------------------------------------------------------------------ painting
    def paintEvent(self, ev):
        p = QPainter(self.viewport())
        p.fillRect(self.viewport().rect(), QColor("#3b3d40") if self.dark_bg else QColor("#d9dbde"))
        if not self.doc:
            return
        first, last = self._visible_range()
        for i in range(first, last + 1):
            ox, oy = self._origin(i)
            r = QRect(ox, oy, self.pw[i], self.ph[i])
            pm = self._pixmap(i)
            p.drawPixmap(r, pm)
            p.setPen(QPen(QColor(0, 0, 0, 70), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r.adjusted(-1, -1, 0, 0))
            self._paint_overlays(p, i)
        self._paint_drag_preview(p)
        p.end()
        if not self._prefetch_timer.isActive():
            self._prefetch_timer.start(25)

    def _paint_overlays(self, p: QPainter, i: int):
        p.setPen(Qt.PenStyle.NoPen)
        # search hits
        for k, (pg, rect) in enumerate(self._hits):
            if pg == i:
                cur = (k == self._hit_idx)
                p.setBrush(QColor(255, 120, 0, 140) if cur else QColor(255, 210, 0, 110))
                p.drawRect(self._rect_px(i, rect))
        # text selection
        if self.sel_words and self.sel_words[0] == i:
            p.setBrush(QColor(61, 126, 255, 85))
            for r in self._selection_rects(*self.sel_words):
                p.drawRect(self._rect_px(i, r))
        # selected annotation
        if self.sel_annot and self.sel_annot[0] == i:
            a = self._annot_info(i, self.sel_annot[1])
            if a and not (self._drag and self._drag.get("kind") in ("move", "resize")):
                p.setBrush(Qt.BrushStyle.NoBrush)
                pen = QPen(QColor("#3d7eff"), 1.5, Qt.PenStyle.DashLine)
                p.setPen(pen)
                rects = a.quads if a.kind in MARKUP and a.quads else [a.rect]
                for r in rects:
                    p.drawRect(self._rect_px(i, r).adjusted(-1, -1, 1, 1))
                if a.kind == A_STAMP:
                    self._paint_handles(p, i, a.rect)
        # comment indicator on markup annotations that carry a comment
        for a in self._get_annots(i):
            if a.kind in MARKUP and a.content.strip() and a.quads:
                q = self._rect_px(i, a.quads[-1])
                p.setPen(QPen(QColor("#b39400"), 1))
                p.setBrush(QColor("#ffe45c"))
                p.drawRoundedRect(QRectF(q.right() + 2, q.top(), 11, 11), 2, 2)
        # sign placement ghost
        if self.tool == "sign" and self.pending_img is not None and self._hover is not None:
            pg = self._page_at(self._hover)
            if pg == i:
                w = self.pending_w_pt * self.s
                h = w * self.pending_img.height() / max(1, self.pending_img.width())
                p.setOpacity(0.6)
                p.drawImage(QRectF(self._hover.x() - w / 2, self._hover.y() - h / 2, w, h), self.pending_img)
                p.setOpacity(1.0)

    def _paint_handles(self, p: QPainter, i: int, rect):
        p.setPen(QPen(QColor("#3d7eff"), 1.5))
        p.setBrush(QColor("white"))
        for h in self._handle_rects(i, rect).values():
            p.drawRect(h)

    def _handle_rects(self, i: int, rect) -> dict:
        r = self._rect_px(i, rect)
        pts = {"tl": r.topLeft(), "tr": r.topRight(), "bl": r.bottomLeft(), "br": r.bottomRight()}
        return {k: QRectF(v.x() - HS / 2, v.y() - HS / 2, HS, HS) for k, v in pts.items()}

    def _paint_drag_preview(self, p: QPainter):
        d = self._drag
        if not d or not self._moved:
            return
        kind = d["kind"]
        if kind in ("move", "resize"):
            i = d["pg"]
            r = self._rect_px(i, d["rect"])
            if d.get("img") is not None:
                p.setOpacity(0.85)
                p.drawImage(r, d["img"])
                p.setOpacity(1.0)
            if kind == "resize" or d.get("stamp"):
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor("#3d7eff"), 1.5, Qt.PenStyle.DashLine))
                p.drawRect(r)
        elif kind == "area":
            r = self._rect_px(d["pg"], d["rect"])
            p.setPen(Qt.PenStyle.NoPen)
            c = QColor(*[int(v * 255) for v in self.hl_color])
            c.setAlpha(110)
            p.setBrush(c)
            p.drawRect(r)

    # ------------------------------------------------------------------ page data helpers
    def _get_words(self, i: int) -> list:
        w = self._words.get(i)
        if w is None:
            w = reading_order(self._page(i).get_text("words"))
            self._words[i] = w
        return w

    def _get_links(self, i: int) -> list:
        l = self._links.get(i)
        if l is None:
            l = self._page(i).get_links()
            self._links[i] = l
        return l

    def _get_annots(self, i: int) -> list[AInfo]:
        lst = self._annots.get(i)
        if lst is not None:
            return lst
        lst = []
        page = self._page(i)
        for a in page.annots():
            t = a.type[0]
            if t == A_POPUP or (i, a.xref) in self.trashed:
                continue
            if a.flags & HIDDEN:
                continue
            quads = []
            if t in MARKUP:
                v = a.vertices or []
                for k in range(0, len(v) - 3, 4):
                    quads.append(pymupdf.Quad(v[k:k + 4]).rect)
            info = a.info
            lst.append(AInfo(a.xref, t, pymupdf.Rect(a.rect), quads,
                             info.get("content", "") or "", info.get("subject", "") or ""))
        self._annots[i] = lst
        return lst

    def _annot_info(self, i: int, xref: int) -> AInfo | None:
        for a in self._get_annots(i):
            if a.xref == xref:
                return a
        return None

    def _find(self, i: int, xref: int):
        for a in self._page(i).annots():
            if a.xref == xref:
                return a
        return None

    def _annot_at(self, i: int, x: float, y: float, skip_markup=False) -> AInfo | None:
        lst = self._get_annots(i)
        tol = 2.0 / max(self.zoom, 0.2)
        for a in reversed(lst):
            if a.kind in (A_STAMP, A_TEXT):
                r = a.rect
                if r.x0 - tol <= x <= r.x1 + tol and r.y0 - tol <= y <= r.y1 + tol:
                    return a
        if not skip_markup:
            for a in reversed(lst):
                if a.kind in MARKUP:
                    for r in a.quads:
                        if r.x0 <= x <= r.x1 and r.y0 <= y <= r.y1:
                            return a
        return None

    def _word_near(self, i: int, x: float, y: float, tol: float):
        best, bd = None, tol * tol
        for k, w in enumerate(self._get_words(i)):
            dx = max(w[0] - x, 0, x - w[2])
            dy = max(w[1] - y, 0, y - w[3])
            d = dx * dx + dy * dy
            if d <= bd:
                best, bd = k, d
                if d == 0:
                    break
        return best

    def _word_start(self, i: int, x: float, y: float):
        """Where a text drag may begin: on a word, or in the margin / gap of its line."""
        wi = self._word_near(i, x, y, 5)
        if wi is not None:
            return wi
        best, bd = None, 45.0
        for k, w in enumerate(self._get_words(i)):
            if w[1] - 2 <= y <= w[3] + 2:               # same text line (vertical band)
                d = max(w[0] - x, 0, x - w[2])
                if d < bd:
                    best, bd = k, d
        return best

    def _word_nearest(self, i: int, x: float, y: float):
        best, bd = None, 1e18
        for k, w in enumerate(self._get_words(i)):
            dx = max(w[0] - x, 0, x - w[2])
            dy = max(w[1] - y, 0, y - w[3])
            d = dx * dx + dy * dy * 4
            if d < bd:
                best, bd = k, d
        return best

    def _link_at(self, i: int, x: float, y: float):
        for l in self._get_links(i):
            r = l.get("from")
            if r and r.x0 <= x <= r.x1 and r.y0 <= y <= r.y1:
                return l
        return None

    def _selection_rects(self, i: int, i0: int, i1: int) -> list:
        words = self._get_words(i)
        groups: dict = OrderedDict()
        for w in words[i0:i1 + 1]:
            key = (w[5], w[6])
            r = groups.get(key)
            if r is None:
                groups[key] = pymupdf.Rect(w[0], w[1], w[2], w[3])
            else:
                r |= pymupdf.Rect(w[0], w[1], w[2], w[3])
        return list(groups.values())

    def selected_text(self) -> str:
        if not self.sel_words:
            return ""
        i, i0, i1 = self.sel_words
        rows: list[list] = []
        last = None
        for w in self._get_words(i)[i0:i1 + 1]:
            key = (w[5], w[6])
            if key != last:
                rows.append([])
                last = key
            rows[-1].append(w)
        lines = []
        for ws in rows:
            if row_is_rtl(ws):
                ws = fix_rtl_row(ws)
            lines.append(" ".join(w[4] for w in ws))
        return "\n".join(lines)

    def has_selection(self) -> bool:
        return self.sel_words is not None

    def copy_selection(self):
        t = self.selected_text()
        if t:
            QApplication.clipboard().setText(t)
            self.statusMessage.emit(T("copied"))

    def clear_selection(self):
        had = self.sel_words is not None or self.sel_annot is not None
        self.sel_words = None
        self.sel_annot = None
        if had:
            self.selectionChanged.emit(False)
            self.viewport().update()

    # ------------------------------------------------------------------ undo / redo / trash
    def _push(self, undo, redo, pages):
        self.undo_stack.append(Cmd(undo, redo, list(pages)))
        self.redo_stack.clear()
        self._set_dirty(True)
        self._invalidate(pages)
        self.undoStateChanged.emit()

    def can_undo(self) -> bool:
        return bool(self.undo_stack)

    def can_redo(self) -> bool:
        return bool(self.redo_stack)

    def undo(self):
        self._close_popup(commit=True)
        if not self.undo_stack:
            return
        c = self.undo_stack.pop()
        c.undo()
        self.redo_stack.append(c)
        self._after_history(c)

    def redo(self):
        self._close_popup(commit=True)
        if not self.redo_stack:
            return
        c = self.redo_stack.pop()
        c.redo()
        self.undo_stack.append(c)
        self._after_history(c)

    def _after_history(self, c: Cmd):
        self.sel_annot = None
        self._set_dirty(True)
        self._invalidate(c.pages)
        self.undoStateChanged.emit()
        self.selectionChanged.emit(False)

    def _hide_raw(self, pg: int, xref: int):
        a = self._find(pg, xref)
        if a:
            a.set_flags(a.flags | HIDDEN)
        self.trashed.add((pg, xref))

    def _show_raw(self, pg: int, xref: int):
        a = self._find(pg, xref)
        if a:
            a.set_flags(a.flags & ~HIDDEN)
        self.trashed.discard((pg, xref))

    def _push_added(self, pg: int, xref: int):
        self._push(lambda: self._hide_raw(pg, xref), lambda: self._show_raw(pg, xref), [pg])

    def _discard_new(self, pg: int, xref: int):
        a = self._find(pg, xref)
        if a:
            self._page(pg).delete_annot(a)
        self._invalidate([pg])

    def delete_annot(self, pg: int, xref: int):
        self._hide_raw(pg, xref)
        self._push(lambda: self._show_raw(pg, xref), lambda: self._hide_raw(pg, xref), [pg])
        if self.sel_annot == (pg, xref):
            self.sel_annot = None
            self.selectionChanged.emit(False)

    def delete_selected(self):
        if self.sel_annot:
            self.delete_annot(*self.sel_annot)

    def purge_trashed(self):
        """Physically remove soft-deleted annotations (call right before saving)."""
        if not self.doc:
            return
        by_page: dict[int, set] = {}
        for pg, xref in self.trashed:
            by_page.setdefault(pg, set()).add(xref)
        for pg, xrefs in by_page.items():
            page = self._page(pg)
            for a in list(page.annots()):
                if a.xref in xrefs:
                    page.delete_annot(a)
        self.trashed.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._annots.clear()
        self.undoStateChanged.emit()

    # ------------------------------------------------------------------ creating annotations
    def _style(self, a, color=None):
        a.set_info(title=self.author or "LitePDF")
        if color is not None:
            a.set_colors(stroke=color)
        a.update()

    def apply_markup(self, kind="highlight", rects=None, comment=False) -> bool:
        """Create a markup annotation from the current text selection (or given rects)."""
        if rects is None:
            if not self.sel_words:
                return False
            pg, i0, i1 = self.sel_words
            rects = self._selection_rects(pg, i0, i1)
        else:
            pg = rects[0]
            rects = rects[1]
        if not rects:
            return False
        page = self._page(pg)
        if kind == "highlight":
            a = page.add_highlight_annot(quads=rects)
            color = self.hl_color
        elif kind == "underline":
            a = page.add_underline_annot(quads=rects)
            color = (0.1, 0.35, 0.95)
        else:
            a = page.add_strikeout_annot(quads=rects)
            color = (0.9, 0.1, 0.1)
        self._style(a, color)
        xref = a.xref
        self._push_added(pg, xref)
        self.sel_words = None
        self.selectionChanged.emit(False)
        if comment:
            self.sel_annot = (pg, xref)
            self._open_comment(pg, xref)
        return True

    def _add_note_at(self, pg: int, x: float, y: float):
        page = self._page(pg)
        r = self.page_rects[pg]
        x = max(0, min(r.width - 18, x - 8))
        y = max(0, min(r.height - 18, y - 8))
        a = page.add_text_annot((x, y), "", icon="Note")
        self._style(a, (1.0, 0.8, 0.0))
        xref = a.xref
        self._invalidate([pg])
        self._open_note_editor(pg, xref, "", new=True)

    def add_stamp(self, pg: int, png: bytes, rect: pymupdf.Rect, content="", subject="") -> int:
        page = self._page(pg)
        a = page.add_stamp_annot(rect, stamp=png)
        a.set_info(title=self.author or "LitePDF", content=content, subject=subject)
        return a.xref

    def _clamp_rect(self, pg: int, rect: pymupdf.Rect) -> pymupdf.Rect:
        pr = self.page_rects[pg]
        dx = dy = 0.0
        if rect.x0 < 0:
            dx = -rect.x0
        elif rect.x1 > pr.width:
            dx = pr.width - rect.x1
        if rect.y0 < 0:
            dy = -rect.y0
        elif rect.y1 > pr.height:
            dy = pr.height - rect.y1
        return pymupdf.Rect(rect.x0 + dx, rect.y0 + dy, rect.x1 + dx, rect.y1 + dy)

    def place_pending_signature(self, pg: int, x: float, y: float):
        if not self.pending_png or self.pending_img is None:
            return
        w = self.pending_w_pt
        h = w * self.pending_img.height() / max(1, self.pending_img.width())
        rect = self._clamp_rect(pg, pymupdf.Rect(x - w / 2, y - h / 2, x + w / 2, y + h / 2))
        xref = self.add_stamp(pg, self.pending_png, rect, content="Signature", subject="litepdf-signature")
        self._push_added(pg, xref)
        self.sel_annot = (pg, xref)
        self.selectionChanged.emit(True)
        self.requestToolReset.emit()

    def _make_text_stamp(self, text: str, preset: str | None = None):
        size = self.text_opts["size"]
        family = self.text_opts["family"]
        if preset in ("check", "cross"):
            family = "Segoe UI Symbol"
            size = max(size, 14)
        img, w, h = render_text(text, size, self.text_opts["color"], family)
        return image_to_png(img), w, h

    def place_text(self, pg: int, x: float, y: float, text: str, preset: str | None = None,
                   replace_xref: int | None = None):
        text = text.rstrip()
        if not text.strip():
            return
        png, w, h = self._make_text_stamp(text, preset)
        rect = self._clamp_rect(pg, pymupdf.Rect(x, y, x + w, y + h))
        tag = f"{TEXT_STAMP_TAG}|{self.text_opts['size']}|{','.join(str(int(c)) for c in self.text_opts['color'])}"
        old = replace_xref
        xref = self.add_stamp(pg, png, rect, content=text, subject=tag)
        if old is not None:
            self._hide_raw(pg, old)
            self._push(lambda: (self._hide_raw(pg, xref), self._show_raw(pg, old)),
                       lambda: (self._show_raw(pg, xref), self._hide_raw(pg, old)), [pg])
        else:
            self._push_added(pg, xref)
        self.sel_annot = (pg, xref)
        self.selectionChanged.emit(True)

    # ------------------------------------------------------------------ popups
    def _close_popup(self, commit=True):
        p = self._popup
        if p is not None:
            self._popup = None
            self._popup_anchor = None
            if commit:
                if isinstance(p, NotePopup):
                    p.finish()
                else:
                    p.finish()
            else:
                p._done = True
                p.hide()
                p.deleteLater()

    def _reposition_popup(self):
        if self._popup is None or self._popup_anchor is None:
            return
        pg, x, y = self._popup_anchor
        if pg >= len(self.tops):
            return
        pt = self._to_px(pg, x, y)
        vp = self.viewport()
        px = int(max(0, min(vp.width() - self._popup.width(), pt.x())))
        py = int(max(0, min(vp.height() - self._popup.height(), pt.y())))
        self._popup.move(px, py)

    def _show_popup(self, popup, pg: int, x: float, y: float):
        self._close_popup(commit=True)
        self._popup = popup
        self._popup_anchor = (pg, x, y)
        popup.setParent(self.viewport())
        popup.show()
        self._reposition_popup()
        popup.raise_()

    def _open_note_editor(self, pg: int, xref: int, text: str, new=False):
        pop = NotePopup(self.viewport(), text, title=self.author or "", deletable=True)
        state = {"deleted": False}

        def committed(t: str):
            if self._popup is pop:
                self._popup = None
            if state["deleted"]:
                return
            if new:
                if t.strip():
                    a = self._find(pg, xref)
                    if a:
                        a.set_info(content=t)
                    self._push_added(pg, xref)
                else:
                    self._discard_new(pg, xref)
            elif t != text:
                self._set_content(pg, xref, t, text)
            self.viewport().setFocus()

        def deleted():
            state["deleted"] = True
            if self._popup is pop:
                self._popup = None
            if new:
                self._discard_new(pg, xref)
            else:
                self.delete_annot(pg, xref)
            self.viewport().setFocus()

        pop.committed.connect(committed)
        pop.deleteRequested.connect(deleted)
        info = self._annot_info(pg, xref)
        r = info.rect if info else pymupdf.Rect(0, 0, 16, 16)
        self._show_popup(pop, pg, r.x1 + 4, r.y0)
        pop.focus_end()

    def _open_comment(self, pg: int, xref: int):
        info = self._annot_info(pg, xref)
        if not info:
            return
        a = info
        pop = NotePopup(self.viewport(), a.content, title=T("comment"), deletable=True,
                        delete_tip=T("delete_markup"))

        def committed(t: str):
            if self._popup is pop:
                self._popup = None
            if t != a.content:
                self._set_content(pg, xref, t, a.content)
            self.viewport().setFocus()

        def deleted():
            if self._popup is pop:
                self._popup = None
            self.delete_annot(pg, xref)
            self.viewport().setFocus()

        pop.committed.connect(committed)
        pop.deleteRequested.connect(deleted)
        last = a.quads[-1] if a.quads else a.rect
        self._show_popup(pop, pg, last.x1 + 6, last.y0)
        pop.focus_end()

    def _set_content_raw(self, pg: int, xref: int, text: str):
        a = self._find(pg, xref)
        if a:
            a.set_info(content=text)

    def _set_content(self, pg: int, xref: int, new: str, old: str):
        self._set_content_raw(pg, xref, new)
        self._push(lambda: self._set_content_raw(pg, xref, old),
                   lambda: self._set_content_raw(pg, xref, new), [pg])

    def _begin_text_input(self, pg: int, x: float, y: float, text="", replace_xref=None, preset=None):
        px = self.text_opts["size"] * self.s
        pop = TextPopup(self.viewport(), text, px, self.text_opts["color"], self.text_opts["family"])

        def committed(t: str):
            if self._popup is pop:
                self._popup = None
            self.place_text(pg, x, y, t, preset, replace_xref)
            self.viewport().setFocus()

        def cancelled():
            if self._popup is pop:
                self._popup = None
            if replace_xref is not None:
                pass
            self.viewport().setFocus()

        pop.committed.connect(committed)
        pop.cancelled.connect(cancelled)
        self._show_popup(pop, pg, x, y)
        pop.focus()

    # ------------------------------------------------------------------ search
    def clear_search(self):
        self._search_text = ""
        self._hits, self._hits_by_page, self._hit_idx = [], {}, -1
        self.viewport().update()

    def search(self, text: str, forward=True, restart=False):
        if not self.doc:
            return
        if not text:
            self.clear_search()
            self.searchResult.emit(0, 0)
            return
        if text != self._search_text or restart:
            self._search_text = text
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                hits = []
                for i in range(self.page_count):
                    for r in self._page(i).search_for(text):
                        hits.append((i, pymupdf.Rect(r)))
                self._hits = hits
            finally:
                QApplication.restoreOverrideCursor()
            self._hit_idx = -1
            if self._hits:
                cp = self._cur_page
                self._hit_idx = next((k for k, h in enumerate(self._hits) if h[0] >= cp), 0)
                self._goto_hit()
        elif self._hits:
            n = len(self._hits)
            self._hit_idx = (self._hit_idx + (1 if forward else -1)) % n
            self._goto_hit()
        self.searchResult.emit(self._hit_idx + 1 if self._hits else 0, len(self._hits))
        self.viewport().update()

    def _goto_hit(self):
        pg, r = self._hits[self._hit_idx]
        vp = self.viewport()
        top = self.tops[pg] + r.y0 * self.s
        self.verticalScrollBar().setValue(int(top - vp.height() / 3))
        ox, _ = self._origin(pg)
        px = ox + r.x0 * self.s
        if px < 0 or px > vp.width() - 40:
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() + px - vp.width() / 2))

    # ------------------------------------------------------------------ rotate / misc
    def rotate_all(self, delta: int):
        if not self.doc:
            return
        self._close_popup(commit=True)
        for p in self.doc:
            p.set_rotation((p.rotation + delta) % 360)
        self._compute_page_rects()
        self._cache.clear()
        self._cache_bytes = 0
        self._words.clear()
        self._annots.clear()
        self._links.clear()
        self.sel_words = self.sel_annot = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.undoStateChanged.emit()
        if self.fit_mode:
            self._apply_fit()
        self._relayout()
        self.goto_page(self._cur_page)
        self.zoomChanged.emit(self.zoom)
        self._set_dirty(True)
        self.viewport().update()

    def collect_notes(self) -> list[tuple[int, int, int, str]]:
        """[(page, xref, kind, text)] for annotations that carry text."""
        out = []
        if not self.doc:
            return out
        for i in range(self.page_count):
            for a in self._get_annots(i):
                if a.kind in (A_TEXT, *MARKUP) and a.content.strip():
                    out.append((i, a.xref, a.kind, a.content))
        return out

    def select_annot(self, pg: int, xref: int):
        self.sel_annot = (pg, xref)
        info = self._annot_info(pg, xref)
        if info:
            self.goto_page(pg, max(0, info.rect.y0 - 80 / self.s))
        self.viewport().update()

    # ------------------------------------------------------------------ tools
    def set_tool(self, name: str):
        self._close_popup(commit=True)
        self.tool = name
        self._update_cursor(self._hover)
        self.viewport().update()

    def _update_cursor(self, pos):
        c = Qt.CursorShape.ArrowCursor
        if self.tool in ("note", "text", "sign"):
            c = Qt.CursorShape.CrossCursor
        elif pos is not None and self.doc:
            pg = self._page_at(pos)
            if pg >= 0:
                x, y = self._to_page(pg, pos)
                if self.sel_annot and self._handle_at(pos):
                    c = Qt.CursorShape.SizeFDiagCursor
                elif self._annot_at(pg, x, y, self.tool in MARKUP_TOOLS):
                    c = Qt.CursorShape.PointingHandCursor
                elif self.tool == "select" and self._link_at(pg, x, y):
                    c = Qt.CursorShape.PointingHandCursor
                elif self._word_near(pg, x, y, 4) is not None:
                    c = Qt.CursorShape.IBeamCursor
                elif self.tool in MARKUP_TOOLS:
                    c = Qt.CursorShape.IBeamCursor
                else:
                    c = Qt.CursorShape.OpenHandCursor
            else:
                c = Qt.CursorShape.OpenHandCursor
        self.viewport().setCursor(c)

    def _handle_at(self, pos) -> str | None:
        if not self.sel_annot:
            return None
        pg, xref = self.sel_annot
        a = self._annot_info(pg, xref)
        if not a or a.kind != A_STAMP:
            return None
        for name, r in self._handle_rects(pg, a.rect).items():
            if r.adjusted(-3, -3, 3, 3).contains(QPointF(pos)):
                return name
        return None

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, ev):
        self.setFocus()
        pos = ev.position().toPoint()
        if self._popup is not None and not self._popup.geometry().contains(pos):
            self._close_popup(commit=True)
        if ev.button() == Qt.MouseButton.MiddleButton:
            self._begin_pan(pos)
            self._moved = True
            return
        if ev.button() != Qt.MouseButton.LeftButton or not self.doc:
            return
        self._press_pos = pos
        self._moved = False
        self._pending_click = None
        h = self._handle_at(pos)
        if h:
            self._begin_resize(h)
            return
        pg = self._page_at(pos)
        if pg < 0:
            self.clear_selection()
            self._begin_pan(pos)
            return
        x, y = self._to_page(pg, pos)
        tool = self.tool
        if tool == "note":
            self._add_note_at(pg, x, y)
            return
        if tool == "text":
            self.clear_selection()
            if self.text_preset:
                txt = {"check": "✓", "cross": "✗"}.get(self.text_preset)
                if self.text_preset == "date":
                    from PySide6.QtCore import QDate
                    txt = QDate.currentDate().toString("dd/MM/yyyy")
                self.place_text(pg, x, y - self.text_opts["size"] * 0.6, txt, self.text_preset)
            else:
                self._begin_text_input(pg, x, y)
            return
        if tool == "sign":
            self.place_pending_signature(pg, x, y)
            return
        # select / markup tools
        a = self._annot_at(pg, x, y, skip_markup=tool in MARKUP_TOOLS)
        self.sel_words = None
        if a is not None:
            if self.sel_annot != (pg, a.xref):
                self.sel_annot = (pg, a.xref)
                self.selectionChanged.emit(True)
            if a.kind in (A_STAMP, A_TEXT):
                self._begin_move(pg, a)
                self.viewport().update()
                return
            self._pending_click = {"type": "annot", "pg": pg, "xref": a.xref}
        else:
            if self.sel_annot:
                self.sel_annot = None
                self.selectionChanged.emit(False)
            link = self._link_at(pg, x, y) if tool == "select" else None
            if link:
                self._pending_click = {"type": "link", "link": link}
        wi = self._word_start(pg, x, y)
        if wi is not None:
            self._drag = {"kind": "select", "pg": pg, "start": wi}
        elif tool == "highlight" and self._pending_click is None:
            self._drag = {"kind": "area", "pg": pg, "x": x, "y": y, "rect": pymupdf.Rect(x, y, x, y)}
        else:
            self._begin_pan(pos)
        self.viewport().update()

    def _begin_pan(self, pos):
        self._drag = {"kind": "pan", "pos": pos,
                      "h": self.horizontalScrollBar().value(), "v": self.verticalScrollBar().value()}
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def _grab_preview(self, pg: int, xref: int):
        a = self._find(pg, xref)
        if not a:
            return None
        rs = self.s * self.devicePixelRatioF()
        try:
            pix = a.get_pixmap(matrix=pymupdf.Matrix(rs, rs), alpha=True)
            img = qimage_from_pix(pix, QImage.Format.Format_RGBA8888)
            return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        except Exception:
            return None

    def _begin_move(self, pg: int, a: AInfo):
        self._drag = {"kind": "move", "pg": pg, "xref": a.xref, "orig": pymupdf.Rect(a.rect),
                      "rect": pymupdf.Rect(a.rect), "stamp": a.kind == A_STAMP, "started": False,
                      "note": a.kind == A_TEXT}

    def _begin_resize(self, handle: str):
        pg, xref = self.sel_annot
        a = self._annot_info(pg, xref)
        self._drag = {"kind": "resize", "pg": pg, "xref": xref, "orig": pymupdf.Rect(a.rect),
                      "rect": pymupdf.Rect(a.rect), "handle": handle, "started": False}

    def _start_hidden_preview(self, d):
        """On first real movement: grab preview and hide the original so it doesn't ghost."""
        if d.get("started"):
            return
        d["started"] = True
        d["img"] = self._grab_preview(d["pg"], d["xref"])
        a = self._find(d["pg"], d["xref"])
        if a:
            a.set_flags(a.flags | HIDDEN)
        self._invalidate_keep_selection(d["pg"])

    def _invalidate_keep_selection(self, pg):
        for k in [k for k in self._cache if k[0] == pg]:
            pm = self._cache.pop(k)
            self._cache_bytes -= pm.width() * pm.height() * 4
        self.viewport().update()

    def mouseMoveEvent(self, ev):
        pos = ev.position().toPoint()
        d = self._drag
        if d is None:
            self._hover = pos
            self._update_cursor(pos)
            if self.tool == "sign":
                self.viewport().update()
            return
        if not self._moved:
            if (pos - self._press_pos).manhattanLength() < 4:
                return
            self._moved = True
        kind = d["kind"]
        if kind == "pan":
            self.horizontalScrollBar().setValue(d["h"] - (pos.x() - d["pos"].x()))
            self.verticalScrollBar().setValue(d["v"] - (pos.y() - d["pos"].y()))
            return
        pg = d["pg"]
        x, y = self._to_page(pg, pos)
        if kind == "select":
            wi = self._word_nearest(pg, x, y)
            if wi is not None:
                a, b = sorted((d["start"], wi))
                self.sel_words = (pg, a, b)
                self._pending_click = None
        elif kind == "area":
            d["rect"] = pymupdf.Rect(min(d["x"], x), min(d["y"], y), max(d["x"], x), max(d["y"], y))
        elif kind == "move":
            self._start_hidden_preview(d)
            dx, dy = (pos.x() - self._press_pos.x()) / self.s, (pos.y() - self._press_pos.y()) / self.s
            o = d["orig"]
            d["rect"] = self._clamp_rect(pg, pymupdf.Rect(o.x0 + dx, o.y0 + dy, o.x1 + dx, o.y1 + dy))
        elif kind == "resize":
            self._start_hidden_preview(d)
            o = d["orig"]
            ar = o.height / max(o.width, 1e-6)
            hname = d["handle"]
            fx = o.x1 if "l" in hname else o.x0
            fy = o.y1 if "t" in hname else o.y0
            w = max(12.0, abs(x - fx))
            h = w * ar
            x0, x1 = (fx - w, fx) if "l" in hname else (fx, fx + w)
            y0, y1 = (fy - h, fy) if "t" in hname else (fy, fy + h)
            d["rect"] = pymupdf.Rect(x0, y0, x1, y1)
        self.viewport().update()

    def mouseReleaseEvent(self, ev):
        d = self._drag
        self._drag = None
        self._update_cursor(ev.position().toPoint())
        if d is None:
            return
        kind = d["kind"]
        pg = d.get("pg")
        if kind in ("move", "resize"):
            self._finish_move(d)
            return
        if kind == "select":
            if self._moved and self.sel_words:
                if self.tool in MARKUP_TOOLS:
                    self.apply_markup({"highlight": "highlight", "underline": "underline",
                                       "strike": "strike"}[self.tool])
                else:
                    self.selectionChanged.emit(True)
            elif not self._moved:
                self._click_action(ev)
        elif kind == "area":
            r = d["rect"]
            if self._moved and r.width > 3 and r.height > 3:
                self.apply_markup("highlight", rects=(pg, [r]))
            elif not self._moved:
                self.clear_selection()
        elif kind == "pan" and not self._moved:
            self.clear_selection()
        self.viewport().update()

    def _click_action(self, ev):
        pc = self._pending_click
        self._pending_click = None
        if pc is None:
            self.sel_words = None
            self.selectionChanged.emit(False)
            return
        if pc["type"] == "link":
            self._follow_link(pc["link"])
        elif pc["type"] == "annot":
            self._open_comment(pc["pg"], pc["xref"])

    def _finish_move(self, d):
        pg, xref = d["pg"], d["xref"]
        if not d.get("started"):
            # plain click on stamp / note
            if d["kind"] == "move" and d.get("note"):
                info = self._annot_info(pg, xref)
                self._open_note_editor(pg, xref, info.content if info else "")
            return
        old, new = pymupdf.Rect(d["orig"]), pymupdf.Rect(d["rect"])
        a = self._find(pg, xref)
        if a:
            a.set_flags(a.flags & ~HIDDEN)
            a.set_rect(new)

        def setr(r):
            b = self._find(pg, xref)
            if b:
                b.set_rect(r)
        self._push(lambda: setr(old), lambda: setr(new), [pg])
        self.viewport().update()

    def mouseDoubleClickEvent(self, ev):
        if not self.doc or ev.button() != Qt.MouseButton.LeftButton:
            return
        pos = ev.position().toPoint()
        pg = self._page_at(pos)
        if pg < 0:
            return
        x, y = self._to_page(pg, pos)
        a = self._annot_at(pg, x, y)
        if a and a.kind == A_STAMP and a.subject.startswith(TEXT_STAMP_TAG):
            self._edit_text_stamp(pg, a)
            return
        if a and a.kind in MARKUP:
            self._open_comment(pg, a.xref)
            return
        wi = self._word_near(pg, x, y, 3)
        if wi is not None:
            self.sel_words = (pg, wi, wi)
            self.selectionChanged.emit(True)
            self.viewport().update()

    def _edit_text_stamp(self, pg: int, a: AInfo):
        parts = a.subject.split("|")
        try:
            self.text_opts["size"] = float(parts[1])
            self.text_opts["color"] = tuple(int(v) for v in parts[2].split(","))
        except Exception:
            pass
        self._begin_text_input(pg, a.rect.x0, a.rect.y0, text=a.content, replace_xref=a.xref)

    def _follow_link(self, link):
        kind = link.get("kind")
        if kind == pymupdf.LINK_GOTO:
            to = link.get("to")
            self.goto_page(link.get("page", 0), to.y if to else 0)
        elif kind == pymupdf.LINK_URI:
            QDesktopServices.openUrl(QUrl(link.get("uri", "")))

    def leaveEvent(self, ev):
        self._hover = None
        self.viewport().update()
        super().leaveEvent(ev)

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            dy = ev.angleDelta().y()
            if dy:
                self.zoom_by(1.1 ** (dy / 120.0), ev.position().toPoint())
            ev.accept()
            return
        px, ang = ev.pixelDelta(), ev.angleDelta()
        horizontal = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if not px.isNull():                       # precision touchpad: already pixel-smooth
            self._stop_anim()
            vb, hb = self.verticalScrollBar(), self.horizontalScrollBar()
            hb.setValue(hb.value() - px.x())
            if horizontal:
                hb.setValue(hb.value() - px.y())
            else:
                vb.setValue(vb.value() - px.y())
        else:                                     # mouse wheel: glide ~110 px per notch
            if horizontal or ang.x():
                hb = self.horizontalScrollBar()
                hb.setValue(hb.value() - int((ang.x() or ang.y()) / 120.0 * 110))
            else:
                self.smooth_scroll_by(-ang.y() / 120.0 * 110)
        ev.accept()

    # ------------------------------------------------------------------ keyboard
    def keyPressEvent(self, ev: QKeyEvent):
        k = ev.key()
        mods = ev.modifiers()
        vb = self.verticalScrollBar()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        if k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.sel_annot:
            self.delete_selected()
        elif k == Qt.Key.Key_Escape:
            if self._drag and self._drag["kind"] in ("move", "resize") and self._drag.get("started"):
                d = self._drag
                self._drag = None
                a = self._find(d["pg"], d["xref"])
                if a:
                    a.set_flags(a.flags & ~HIDDEN)
                self._invalidate([d["pg"]])
            self._drag = None
            self.clear_selection()
            self.toolShortcut.emit("select")
        elif ctrl and k == Qt.Key.Key_C:
            self.copy_selection()
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) and self.sel_annot:
            self._nudge(k, 10.0 if mods & Qt.KeyboardModifier.ShiftModifier else 1.0)
        elif k == Qt.Key.Key_Down:
            self.smooth_scroll_by(80)
        elif k == Qt.Key.Key_Up:
            self.smooth_scroll_by(-80)
        elif k == Qt.Key.Key_Left:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - 60)
        elif k == Qt.Key.Key_Right:
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + 60)
        elif k in (Qt.Key.Key_PageDown, Qt.Key.Key_Space):
            self.smooth_scroll_by(vb.pageStep() - 40)
        elif k == Qt.Key.Key_PageUp:
            self.smooth_scroll_by(-(vb.pageStep() - 40))
        elif k == Qt.Key.Key_Home and self.doc:
            self.goto_page(0)
        elif k == Qt.Key.Key_End and self.doc:
            self.goto_page(self.page_count - 1)
        elif not ctrl and k in (Qt.Key.Key_V, Qt.Key.Key_H, Qt.Key.Key_N, Qt.Key.Key_T, Qt.Key.Key_S):
            self.toolShortcut.emit({Qt.Key.Key_V: "select", Qt.Key.Key_H: "highlight",
                                    Qt.Key.Key_N: "note", Qt.Key.Key_T: "text",
                                    Qt.Key.Key_S: "sign"}[k])
        else:
            super().keyPressEvent(ev)

    def _nudge(self, key, step):
        pg, xref = self.sel_annot
        a = self._annot_info(pg, xref)
        if not a or a.kind not in (A_STAMP, A_TEXT):
            return
        dx = {Qt.Key.Key_Left: -step, Qt.Key.Key_Right: step}.get(key, 0)
        dy = {Qt.Key.Key_Up: -step, Qt.Key.Key_Down: step}.get(key, 0)
        old = pymupdf.Rect(a.rect)
        new = self._clamp_rect(pg, pymupdf.Rect(old.x0 + dx, old.y0 + dy, old.x1 + dx, old.y1 + dy))

        def setr(r):
            b = self._find(pg, xref)
            if b:
                b.set_rect(r)
        setr(new)
        self._push(lambda: setr(old), lambda: setr(new), [pg])

    # ------------------------------------------------------------------ context menu
    def contextMenuEvent(self, ev):
        if not self.doc:
            return
        pos = ev.pos()
        pg = self._page_at(pos)
        m = QMenu(self)
        if self.sel_words:
            m.addAction(T("copy"), self.copy_selection)
            m.addSeparator()
            for name, col in HL_COLORS:
                act = m.addAction(T("hl_" + name))
                act.triggered.connect(lambda _=False, c=col: self._ctx_highlight(c))
            m.addAction(T("underline"), lambda: self.apply_markup("underline"))
            m.addAction(T("strike"), lambda: self.apply_markup("strike"))
            m.addAction(T("highlight_comment"), self._ctx_highlight_comment)
        elif pg >= 0:
            x, y = self._to_page(pg, pos)
            a = self._annot_at(pg, x, y)
            if a:
                self.sel_annot = (pg, a.xref)
                self.selectionChanged.emit(True)
                self.viewport().update()
                if a.kind == A_STAMP and a.subject.startswith(TEXT_STAMP_TAG):
                    m.addAction(T("edit_text"), lambda: self._edit_text_stamp(pg, a))
                if a.kind in MARKUP:
                    m.addAction(T("comment"), lambda: self._open_comment(pg, a.xref))
                if a.kind == A_TEXT:
                    m.addAction(T("edit_note"), lambda: self._open_note_editor(pg, a.xref, a.content))
                m.addAction(T("delete"), self.delete_selected)
            else:
                m.addAction(T("add_note_here"), lambda: self._add_note_at(pg, x, y))
                m.addAction(T("add_text_here"), lambda: self._begin_text_input(pg, x, y))
        if m.isEmpty():
            return
        m.exec(ev.globalPos())

    def _ctx_highlight(self, color):
        self.hl_color = color
        self.apply_markup("highlight")

    def _ctx_highlight_comment(self):
        self.apply_markup("highlight", comment=True)
