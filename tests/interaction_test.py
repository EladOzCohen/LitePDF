"""More interaction coverage: tool drags, inline text popup, edit-by-double-click, encrypted + big docs."""
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
OUT = sys.argv[1]

import pymupdf
from PySide6.QtCore import Qt, QPoint, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication([])
import i18n
import strings  # noqa
from main_window import MainWindow
from canvas import A_HL, A_STAMP, A_TEXT

failed = False


def check(cond, msg):
    global failed
    print(("PASS " if cond else "FAIL ") + msg)
    failed = failed or not cond


sample = os.path.join(OUT, "sample.pdf")
work = os.path.join(OUT, "inter_work.pdf")
shutil.copy(sample, work)
settings = QSettings(os.path.join(OUT, "inter.ini"), QSettings.Format.IniFormat)
settings.clear()
win = MainWindow(settings)
win.show()
win.open_path(work)
QTest.qWait(200)
c = win.canvas
vp = c.viewport()


def px(pg, x, y):
    p = c._to_px(pg, x, y)
    return QPoint(int(p.x()), int(p.y()))


def drag(a, b, mods=Qt.KeyboardModifier.NoModifier):
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, mods, a)
    for k in range(1, 9):
        QTest.mouseMove(vp, QPoint(a.x() + (b.x() - a.x()) * k // 8, a.y() + (b.y() - a.y()) * k // 8))
        QApplication.processEvents()
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, mods, b)
    QApplication.processEvents()


# 1. highlight tool: drag over text creates a highlight automatically
w = c._get_words(0)
a_w = next(x for x in w if x[4].startswith("service"))
b_w = next(x for x in w if x[4].startswith("deliver"))
win.set_tool("highlight")
drag(px(0, a_w[0] + 1, (a_w[1] + a_w[3]) / 2), px(0, b_w[2] - 1, (b_w[1] + b_w[3]) / 2))
n_hl = len([a for a in c._get_annots(0) if a.kind == A_HL])
check(n_hl == 1, "highlight tool: drag over text creates highlight")

# 2. area highlight on empty region (no words) with highlight tool
drag(px(0, 100, 200), px(0, 300, 260))
check(len([a for a in c._get_annots(0) if a.kind == A_HL]) == 2, "highlight tool: drag on empty area -> rectangle highlight")

# 3. clicking a highlight (select tool) opens the comment editor; typing a comment stores it
win.set_tool("select")
hl = [a for a in c._get_annots(0) if a.kind == A_HL][0]
r = hl.quads[0]
QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, px(0, (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))
QApplication.processEvents()
check(c._popup is not None, "click on highlight opens comment popup")
c._popup.edit.setPlainText("הערה על הסימון")
c._popup.finish()
QApplication.processEvents()
hl2 = [a for a in c._get_annots(0) if a.kind == A_HL][0]
check(hl2.content == "הערה על הסימון", "highlight comment stored (Hebrew)")

# 4. text tool: click, popup appears, type Hebrew, Enter -> stamp
win.set_tool("text")
c.text_preset = None
c.text_opts["size"] = 13
QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, px(0, 80, 600))
QApplication.processEvents()
check(c._popup is not None, "text tool opens input popup")
QTest.keyClicks(c._popup.edit, "abc")
c._popup.edit.setPlainText("שם: אלעד")
QTest.keyClick(c._popup.edit, Qt.Key.Key_Return)
QApplication.processEvents()
stamps = [a for a in c._get_annots(0) if a.kind == A_STAMP]
check(len(stamps) == 1 and stamps[0].content == "שם: אלעד", "text stamp created with source text kept")

# 5. double-click the text stamp -> editor prefilled -> change -> replaces (old hidden)
win.set_tool("select")
s = stamps[0]
QTest.mouseDClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                  px(0, (s.rect.x0 + s.rect.x1) / 2, (s.rect.y0 + s.rect.y1) / 2))
QApplication.processEvents()
check(c._popup is not None and c._popup.text() == "שם: אלעד", "double-click opens prefilled text editor")
c._popup.edit.setPlainText("שם: אלעד כהן")
c._popup.finish()
QApplication.processEvents()
stamps = [a for a in c._get_annots(0) if a.kind == A_STAMP]
check(len(stamps) == 1 and stamps[0].content == "שם: אלעד כהן", "edited text replaced the old stamp")
c.undo()
stamps = [a for a in c._get_annots(0) if a.kind == A_STAMP]
check(len(stamps) == 1 and stamps[0].content == "שם: אלעד", "undo restores previous text")
c.redo()

# 6. Ctrl+wheel zoom, fit page, goto
before = c.zoom
from PySide6.QtGui import QWheelEvent
from PySide6.QtCore import QPointF, QPoint as QP
ev = QWheelEvent(QPointF(300, 300), QPointF(300, 300), QP(0, 0), QP(0, 120), Qt.MouseButton.NoButton,
                 Qt.KeyboardModifier.ControlModifier, Qt.ScrollPhase.NoScrollPhase, False)
app.sendEvent(vp, ev)
check(c.zoom > before, "ctrl+wheel zooms in")
c.fit_page()
check(c.fit_mode == "page" and c.zoom < before * 1.2, "fit page works")
c.goto_page(2)
QApplication.processEvents()
check(c.current_page == 2, "goto page 3")

# 7. save -> reopen -> still editable (stamp text still re-editable after reload)
check(win._write(work), "save ok")
c = win.canvas
d = pymupdf.open(work)
check(any(a.info.get("subject", "").startswith("litepdf-text") for a in d[0].annots()), "text-stamp tag persisted")
d.close()

# 8. encrypted PDF: open with password, annotate, save
enc = os.path.join(OUT, "enc.pdf")
src = pymupdf.open(sample)
src.save(enc, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="1234", owner_pw="1234")
src.close()
from PySide6.QtWidgets import QInputDialog
orig = QInputDialog.getText
QInputDialog.getText = staticmethod(lambda *a, **k: ("1234", True))
win.open_path(enc)
QInputDialog.getText = orig
c = win.canvas
check(c.doc is not None and os.path.normcase(c.path) == os.path.normcase(os.path.abspath(enc)), "encrypted pdf opened with password")
c.apply_markup("highlight", rects=(0, [pymupdf.Rect(60, 100, 200, 120)]))
ok = win._write(enc)
d = pymupdf.open(enc)
check(d.needs_pass and d.authenticate("1234") and len(list(d[0].annots())) == 1, "encrypted pdf saved, still encrypted, annotation present")
d.close()

# 9. big document performance
big = os.path.join(OUT, "big.pdf")
bd = pymupdf.open()
for i in range(400):
    p = bd.new_page()
    p.insert_text((72, 100), f"Page {i + 1} lorem ipsum dolor sit amet", fontsize=12)
    for k in range(40):
        p.insert_text((72, 130 + k * 14), "The quick brown fox jumps over the lazy dog " * 2, fontsize=9)
bd.save(big)
bd.close()
t0 = time.time()
win.open_path(big)
QApplication.processEvents()
t1 = time.time()
print(f"open 400 pages: {t1 - t0:.2f}s")
check(t1 - t0 < 3.0, "400-page doc opens in < 3 s")
t0 = time.time()
for pg in (0, 150, 399, 200):
    c.goto_page(pg)
    QApplication.processEvents()
print(f"4 jumps (render): {time.time() - t0:.2f}s")
t0 = time.time()
c.search("Page 399")
print(f"search 400 pages: {time.time() - t0:.2f}s hits={len(c._hits)}")
check(len(c._hits) >= 1, "search finds text in big doc")
win.canvas.set_document(None, None)
print("FAILED" if failed else "ALL OK")
