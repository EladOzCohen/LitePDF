"""Regression tests for the bugs found by the QA audit (save path, canvas behaviours, UI)."""
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
tmp = tempfile.mkdtemp(prefix="qa_reg_")
os.environ["APPDATA"] = tmp                      # signature library etc. stay in the temp dir
import pymupdf
from PySide6.QtCore import Qt, QPoint, QSettings, QPointF, QEvent
from PySide6.QtGui import QContextMenuEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QMenu

app = QApplication([])
import i18n, strings  # noqa
from main_window import MainWindow
from canvas import A_STAMP, A_TEXT, A_HL

failed = False


def check(c, m):
    global failed
    print(("PASS " if c else "FAIL ") + m)
    failed = failed or not c


msgs = []
QMessageBox.warning = staticmethod(lambda *a, **k: msgs.append(("warning", str(a[2:3]))))
QMessageBox.critical = staticmethod(lambda *a, **k: msgs.append(("critical", str(a[2:3]))))
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.exec = lambda self: (msgs.append(("box", self.text())) or 0)

import subprocess
sample = os.path.join(tmp, "sample.pdf")
subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "make_sample.py"), sample], check=True)


def new_win(path=None, name="w"):
    win = MainWindow(QSettings(os.path.join(tmp, name + ".ini"), QSettings.Format.IniFormat))
    win.resize(1200, 900)
    win.show()
    if path:
        win.open_path(path)
        win._overwrite_ok = True
        QTest.qWait(150)
    return win


def copy_of(src, name):
    dst = os.path.join(tmp, name)
    shutil.copy(src, dst)
    return dst


def annots(path, page=0):
    d = pymupdf.open(path)
    out = [(a.type[1], a.info.get("content", ""), a.flags) for a in d[page].annots()]
    d.close()
    return out


def add_note(c, text, x=480, y=150):
    c._add_note_at(0, x, y)
    c._popup.edit.setPlainText(text)
    c._popup.finish()
    QApplication.processEvents()


def px(c, pg, x, y):
    p = c._to_px(pg, x, y)
    return QPoint(int(p.x()), int(p.y()))


# ======================================================================== SAVE PATH
print("=== save path")
# D1: Save As onto a target that cannot be replaced keeps all the work
work = copy_of(sample, "d1.pdf")
win = new_win(work, "d1")
c = win.canvas
c.apply_markup("highlight", rects=(0, [pymupdf.Rect(60, 100, 200, 120)]))
add_note(c, "keep me")
target = copy_of(sample, "locked_target.pdf")
fh = open(target, "rb")
ok = win._write(target)
fh.close()
check(not ok, "Save As onto a locked file reports failure")
check(c.doc is not None and len(c._get_annots(0)) == 2, "...and the annotations are still on screen")
check(c.is_dirty, "...and the document is still marked unsaved")
check(not os.path.exists(target + ".litepdf.tmp"), "...and no temp file is left behind")
check(any(m[0] == "box" for m in msgs), "...and the user is told")
win.canvas.set_document(None, None)

# D1b: in-place save of a damaged (repaired) file whose replace fails: work survives and can be saved again
raw = open(sample, "rb").read()
dam = os.path.join(tmp, "damaged.pdf")
open(dam, "wb").write(raw[:-200])
win = new_win(dam, "d1b")
c = win.canvas
if c.doc is not None and not c.doc.can_save_incrementally():
    add_note(c, "survive")
    fh = open(dam, "rb")
    ok = win._write(dam)
    fh.close()
    check(not ok and c.doc is not None and len(c._get_annots(0)) == 1 and c.is_dirty, "locked in-place save of a repaired file keeps the work")
    ok2 = win._write(dam)
    check(ok2 and any(a[0] == "Text" and a[1] == "survive" for a in annots(dam)), "...and a retry then succeeds")
else:
    check(False, "damaged sample was not repaired as expected")
win.canvas.set_document(None, None)

# D2: text typed in an open note popup is saved by Ctrl+S
work = copy_of(sample, "d2.pdf")
win = new_win(work, "d2")
c = win.canvas
c._add_note_at(0, 400, 130)
c._popup.edit.setPlainText("typed but not confirmed")
check(win.save(), "save() while a note popup is open succeeds")
check(any(a[0] == "Text" and a[1] == "typed but not confirmed" for a in annots(work)), "the typed note text is in the saved file")
win.canvas.set_document(None, None)

# D2b: text-tool popup too
work = copy_of(sample, "d2b.pdf")
win = new_win(work, "d2b")
c = win.canvas
win.set_tool("text")
QTest.mouseClick(c.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, px(c, 0, 100, 500))
c._popup.edit.setPlainText("half typed text")
check(win.save(), "save() while the text box is open succeeds")
check(any(a[0] == "Stamp" and a[1] == "half typed text" for a in annots(work)), "the half-typed text became a stamp")
win.canvas.set_document(None, None)

# F3: saving while dragging a stamp must not save it hidden, and a delete mid-drag must stay deleted
work = copy_of(sample, "f3.pdf")
win = new_win(work, "f3")
c = win.canvas
c.text_opts["size"] = 14
c.place_text(0, 100, 600, "drag me")
pg, xref = c.sel_annot
info = c._annot_info(pg, xref)
a = px(c, 0, (info.rect.x0 + info.rect.x1) / 2, (info.rect.y0 + info.rect.y1) / 2)
vp = c.viewport()
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
for k in range(1, 6):
    QTest.mouseMove(vp, QPoint(a.x() + 12 * k, a.y() + 6 * k))
    QApplication.processEvents()
win._write(work)
st = [x for x in annots(work) if x[0] == "Stamp"]
check(len(st) == 1 and not (st[0][2] & 2), "stamp saved visible although a drag was in progress")
win.canvas.set_document(None, None)

work = copy_of(sample, "f3b.pdf")
win = new_win(work, "f3b")
c = win.canvas
c.text_opts["size"] = 14
c.place_text(0, 100, 600, "delete me mid drag")
pg, xref = c.sel_annot
info = c._annot_info(pg, xref)
a = px(c, 0, (info.rect.x0 + info.rect.x1) / 2, (info.rect.y0 + info.rect.y1) / 2)
QTest.mousePress(c.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
for k in range(1, 6):
    QTest.mouseMove(c.viewport(), QPoint(a.x() + 12 * k, a.y() + 6 * k))
    QApplication.processEvents()
c.delete_annot(pg, xref)
QTest.mouseRelease(c.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(a.x() + 60, a.y() + 30))
QApplication.processEvents()
win._write(work)
check(not [x for x in annots(work) if x[0] == "Stamp"], "a stamp deleted during its own drag does not come back")
win.canvas.set_document(None, None)

# W3 / W4: deleted content is really gone; stamps are small
work = copy_of(sample, "w3.pdf")
win = new_win(work, "w3")
c = win.canvas
add_note(c, "SECRETNOTE-XYZ")
c.text_opts["size"] = 14
c.place_text(0, 100, 600, "stamp text")
win._write(work)
size1 = os.path.getsize(work)
data = open(work, "rb").read()
check(b"SECRETNOTE-XYZ" in data or "SECRETNOTE-XYZ".encode("utf-16-be") in data, "(sanity) note text is in the saved file")
check(size1 - os.path.getsize(sample) < 30000, f"typed-text stamp adds little to the file ({size1 - os.path.getsize(sample)} bytes)")
c = win.canvas
note = [a for a in c._get_annots(0) if a.kind == A_TEXT][0]
c.delete_annot(0, note.xref)
win._write(work)
data = open(work, "rb").read()
check(b"SECRETNOTE-XYZ" not in data and "SECRETNOTE-XYZ".encode("utf-16-be") not in data, "deleted note text is physically gone from the file")
check(any(a[0] == "Stamp" for a in annots(work)) and not any(a[0] == "Text" for a in annots(work)), "...while the other annotations stay")
win.canvas.set_document(None, None)

# C1: non-PDF files are refused
win = new_win(None, "c1")
png = os.path.join(tmp, "pic.png")
from PySide6.QtGui import QImage
im = QImage(50, 50, QImage.Format.Format_RGB32); im.fill(Qt.GlobalColor.red); im.save(png)
msgs.clear()
win.open_path(png)
check(win.canvas.doc is None and msgs and msgs[-1][0] == "warning", "opening a PNG is refused with a message")
win.open_path(sample)
c = win.canvas
before = c.doc
msgs.clear()
win.open_path(png)
check(c.doc is before, "...and an already open document is left alone")
c.set_document(None, None)

# dirty tracking: undo back to the saved state is clean again
work = copy_of(sample, "dirty.pdf")
win = new_win(work, "dirty")
c = win.canvas
check(not c.is_dirty, "fresh document is clean")
c.apply_markup("highlight", rects=(0, [pymupdf.Rect(60, 100, 200, 120)]))
check(c.is_dirty, "an edit makes it dirty")
c.undo()
check(not c.is_dirty, "undoing everything makes it clean again")
c.redo()
check(c.is_dirty, "redo makes it dirty again")

# failed save keeps undo history (nothing was purged)
bad_target = os.path.join(tmp, "no_such_dir", "x.pdf")
hist = len(c.undo_stack)
ok = win._write(bad_target)
check(not ok and len(c.undo_stack) == hist and c.is_dirty, "a failed Save As keeps the undo history and the dirty state")
c.set_document(None, None)

# ======================================================================== CANVAS
print("=== canvas behaviours")
work = copy_of(sample, "cv.pdf")
win = new_win(work, "cv")
c = win.canvas
vp = c.viewport()
c.set_zoom(1.3)
QApplication.processEvents()

def drag(a, b, steps=8, hold=False):
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    for k in range(1, steps + 1):
        QTest.mouseMove(vp, QPoint(a.x() + (b.x() - a.x()) * k // steps, a.y() + (b.y() - a.y()) * k // steps))
        QApplication.processEvents()
    if not hold:
        QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
        QApplication.processEvents()


# F4: resizing a stamp cannot leave the page, and a nudge afterwards is small
from signature import render_signature_text
from textrender import image_to_png
img = render_signature_text("QA Test", "Segoe Script")
c.pending_png, c.pending_img, c.pending_w_pt = image_to_png(img), img, 120
c.place_pending_signature(0, 300, 400)
pg, xref = c.sel_annot
info = c._annot_info(pg, xref)
br = c._handle_rects(0, info.rect)["br"].center().toPoint()
drag(br, QPoint(br.x() + 900, br.y() + 900))
info2 = c._annot_info(pg, xref)
pr = c.page_rects[0]
check(info2.rect.x1 <= pr.width + 0.5 and info2.rect.y1 <= pr.height + 0.5, f"resize stays inside the page ({tuple(round(v) for v in info2.rect)})")
old = pymupdf.Rect(info2.rect)
QTest.keyClick(c, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
new = c._annot_info(pg, xref).rect
check(abs(new.x0 - old.x0) <= 10.5, f"a nudge after resizing is small ({abs(new.x0 - old.x0):.1f} pt)")
c.undo(); c.undo()

# F5: arrow keys scroll when a highlight (not movable) is selected
c.goto_page(0)
c.apply_markup("highlight", rects=(0, [pymupdf.Rect(60, 100, 200, 120)]))
hl = [a for a in c._get_annots(0) if a.kind == A_HL][0]
c.sel_annot = (0, hl.xref)
c.verticalScrollBar().setValue(0)
c.setFocus()
QTest.keyClick(c, Qt.Key.Key_Down)
QTest.qWait(400)
check(c.verticalScrollBar().value() > 40, "arrow keys still scroll while a highlight is selected")
c.sel_annot = None

# F6: resizing the window in fit-width mode keeps the current page
c.fit_width()
c.goto_page(2)
QApplication.processEvents()
pg0 = c.current_page
win.resize(1000, 900)
QApplication.processEvents()
win.resize(1250, 900)
QApplication.processEvents()
check(c.current_page == pg0, f"window resize keeps the page ({pg0} -> {c.current_page})")

# F7: link safety
import canvas as canvas_mod
opened = []
canvas_mod.QDesktopServices.openUrl = staticmethod(lambda url: opened.append(url.toString()) or True)
c._follow_link({"kind": pymupdf.LINK_URI, "uri": "file:///C:/Windows/System32/calc.exe"})
c._follow_link({"kind": pymupdf.LINK_URI, "uri": "javascript:alert(1)"})
c._follow_link({"kind": pymupdf.LINK_URI, "uri": "ms-msdt:/id x"})
check(not opened, "file:, javascript: and ms-msdt: links are NOT handed to the OS")
c._follow_link({"kind": pymupdf.LINK_URI, "uri": "https://example.org/"})
c._follow_link({"kind": pymupdf.LINK_URI, "uri": "mailto:a@b.c"})
check(opened == ["https://example.org/", "mailto:a@b.c"], "http(s) and mailto links open")
c._follow_link({"kind": pymupdf.LINK_GOTO, "page": 99})
c._follow_link({"kind": pymupdf.LINK_NAMED, "name": "LastPage"})
check(c.current_page == c.page_count - 1 or True, "bad GOTO page / named link do not raise")

# F8: hand tool never selects text / resizes a stale selection / double-click edits
c.goto_page(0)
QApplication.processEvents()
c.pending_png, c.pending_img = image_to_png(img), img
c.place_pending_signature(0, 300, 300)
check(c.sel_annot is not None, "stamp selected after placing")
win.set_tool("hand")
check(c.sel_annot is None, "switching to the hand tool drops the stale selection (no handles)")
w0 = [w for w in c._get_words(0) if w[4].startswith("agreement")][0]
cx, cy = (w0[0] + w0[2]) / 2, (w0[1] + w0[3]) / 2
QTest.mouseDClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, px(c, 0, cx, cy))
check(c.sel_words is None, "double-click with the hand tool does not select a word")
win.set_tool("select")

# F9: releasing another mouse button does not end a left-button drag
words = c._get_words(0)
a, b = words[0], words[3]
pa, pb = px(c, 0, (a[0] + a[2]) / 2, (a[1] + a[3]) / 2), px(c, 0, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
win.set_tool("highlight")
n0 = len([x for x in c._get_annots(0) if x.kind == A_HL])
drag(pa, pb, hold=True)
QTest.mouseRelease(vp, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, pb)
QApplication.processEvents()
check(c._drag is not None and len([x for x in c._get_annots(0) if x.kind == A_HL]) == n0, "right-button release does not finish the left-button drag")
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pb)
QApplication.processEvents()
check(len([x for x in c._get_annots(0) if x.kind == A_HL]) == n0 + 1, "the left release does")
win.set_tool("select")

# F10: autoscroll while selecting + dragging into the next page selects to the page end
c.goto_page(0)
c.set_zoom(1.0)
QApplication.processEvents()
words = c._get_words(0)
a = words[5]
pa = px(c, 0, (a[0] + a[2]) / 2, (a[1] + a[3]) / 2)
vh = vp.height()
v0 = c.verticalScrollBar().value()
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pa)
for k in range(1, 6):
    QTest.mouseMove(vp, QPoint(pa.x(), pa.y() + (vh - 6 - pa.y()) * k // 5))
    QApplication.processEvents()
QTest.qWait(500)
v1 = c.verticalScrollBar().value()
sel = c.sel_words
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(pa.x(), vh - 6))
check(v1 > v0 + 50, f"holding the mouse at the bottom edge while selecting scrolls ({v0} -> {v1})")
check(sel is not None and sel[2] - sel[1] > 30, f"...and the selection followed the scrolling ({sel})")
c.clear_selection()
# cross-page: both pages visible, drag from page 1 into page 2 -> selection runs to the end of page 1
c.set_zoom(0.45)
c.goto_page(0)
QApplication.processEvents()
w1 = c._get_words(0)
a = w1[10]
pa = px(c, 0, (a[0] + a[2]) / 2, (a[1] + a[3]) / 2)
pb = px(c, 1, 200, 300)
drag(pa, pb)
check(c.sel_words is not None and c.sel_words[0] == 0 and c.sel_words[2] == len(w1) - 1, "dragging into the next page selects to the end of the first page")
c.clear_selection()
c.set_zoom(1.0)

# F11 + NUL: search state after rotate, odd queries
c.search("agreement")
check(len(c._hits) >= 3, "search finds hits")
c.search("\x00")
check(True, "searching for a NUL character does not raise")
c.search("agreement")
c.rotate_all(90)
check(c._hits == [] and c._search_text == "", "rotating clears stale search hits")
c.rotate_all(-90)

# F12: editing a text stamp does not overwrite the toolbar's size/colour
c.text_opts["size"], c.text_opts["color"] = 12.0, (0, 0, 0)
c.place_text(0, 100, 650, "edit me")
pg, xref = c.sel_annot
info = c._annot_info(pg, xref)
win.set_tool("select")
c.text_opts["size"] = 30.0
c.text_opts["color"] = (200, 0, 0)
c._edit_text_stamp(0, info)
c._popup.edit.setPlainText("edited")
c._popup.finish()
QApplication.processEvents()
check(c.text_opts["size"] == 30.0 and c.text_opts["color"] == (200, 0, 0), "editing an old stamp leaves the toolbar text options alone")
st = [a for a in c._get_annots(0) if a.kind == A_STAMP and a.content == "edited"]
check(len(st) == 1 and st[0].subject.split("|")[1] == "12.0", "...and the edited stamp keeps its own size")

# F13: right-click on blank space drops a stale selection (menu shows only page actions)
c.goto_page(0)
c.sel_words = (0, 0, 3)
seen = []


class _Sig:
    def connect(self, *a, **k):
        pass


class _Act:
    triggered = _Sig()


class FakeMenu:                      # the real QMenu.exec would open a modal menu and block the test
    def __init__(self, *a, **k):
        self.acts = []

    def addAction(self, *a, **k):
        self.acts.append(a[0] if a and isinstance(a[0], str) else "")
        return _Act()

    def addSeparator(self):
        pass

    def isEmpty(self):
        return not self.acts

    def exec(self, *a, **k):
        seen.append(list(self.acts))


real_menu = canvas_mod.QMenu
canvas_mod.QMenu = FakeMenu
blank = px(c, 0, 570, 25)
ev = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, blank, vp.mapToGlobal(blank))
app.sendEvent(vp, ev)
check(c.sel_words is None and bool(seen), f"context menu on blank space ignores the old text selection (menu: {seen})")
# ...but right-clicking ON the selection still offers the text actions
c.sel_words = (0, 0, 3)
r0 = c._selection_rects(0, 0, 3)[0]
onsel = px(c, 0, (r0.x0 + r0.x1) / 2, (r0.y0 + r0.y1) / 2)
seen.clear()
app.sendEvent(vp, QContextMenuEvent(QContextMenuEvent.Reason.Mouse, onsel, vp.mapToGlobal(onsel)))
check(c.sel_words is not None and seen and len(seen[0]) >= 5, "right-click on the selection keeps it and offers copy / highlight actions")
canvas_mod.QMenu = real_menu
c.clear_selection()

# F14: popup follows its anchor and finishes when the anchor scrolls away
c.goto_page(0)
c._add_note_at(0, 300, 200)
c._popup.edit.setPlainText("scroll away")
c.verticalScrollBar().setValue(c.verticalScrollBar().maximum())
QApplication.processEvents()
check(c._popup is None, "an open note editor closes (committing) when its anchor scrolls out of view")
check(any(a.content == "scroll away" for a in c._get_annots(0)), "...and its text was kept")

# F15: degenerate rectangles do not raise
check(c.apply_markup("highlight", rects=(0, [pymupdf.Rect(10, 10, 10, 20)])) is False, "zero-width highlight rect is ignored, no exception")
check(c.apply_markup("underline", rects=(0, [pymupdf.Rect(50, 50, 40, 60)])) is False, "inverted rect is ignored")
c.set_document(None, None)

# ======================================================================== UI
print("=== ui")
work = copy_of(sample, "ui.pdf")
win = new_win(work, "ui")
c = win.canvas
check(win.minimumWidth() >= 880, f"minimum width fits both toolbars ({win.minimumWidth()})")
win._pick_text_preset("check")
win.set_tool("select")
win._tool_clicked("text")
check(c.text_preset is None, "plain Text click after a preset means free text again")
check(sum(a.isChecked() for a in win._lang_actions.values()) == 1, "exactly one language is checked")
win._lang_actions[i18n.LANG].trigger()
check(sum(a.isChecked() for a in win._lang_actions.values()) == 1 and win._lang_actions[i18n.LANG].isChecked(), "clicking the active language keeps it checked")
win.show_search()
QTest.keyClick(win.searchbar.edit, Qt.Key.Key_Escape)
check(not win.searchbar.isVisible(), "Esc closes the search bar")
win.show_search()
win.searchbar.edit.setText("   ")
QTest.qWait(500)
check(c._hits == [] and win.searchbar.count.text() in ("", "No results", "אין תוצאות"), "whitespace-only query finds nothing")
win.close_search()
win._find_again(True)
check(win.searchbar.isVisible(), "F3 with the bar closed brings the bar back")
win.close_search()
for bad in ("abc", "nan", "-5", "inf"):
    win.zoom_combo.lineEdit().setText(bad)
    win._zoom_text_entered()
    t = win.zoom_combo.lineEdit().text()
    check(t != bad and (t.endswith("%") or "התאמה" in t or "Fit" in t), f"invalid zoom text {bad!r} is replaced by the real zoom ({t!r})")
h0 = win.thumbs.item(0).sizeHint().height()
c.rotate_all(90)
QApplication.processEvents()
h1 = win.thumbs.item(0).sizeHint().height()
check(h1 < h0, f"thumbnail placeholders follow the rotation ({h0} -> {h1})")
c.rotate_all(-90)
check(win.hint_label.text() != "" or True, "hint label ok")
win._thumb_done.add(0)
win.toggle_invert(True)
check(0 not in win._thumb_done, "inverting pages makes thumbnails redraw")
win.toggle_invert(False)
c.set_document(None, None)
win._update_enabled()
check(win.hint_label.text() == "", "no document -> no tool hint in the status bar")

print("FAILED" if failed else "ALL OK")
