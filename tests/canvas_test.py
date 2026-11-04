"""Drive PdfCanvas with synthetic input and save screenshots + assertions. Run with -X utf8."""
import os
import sys
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
OUT = sys.argv[1]

import pymupdf
from PySide6.QtCore import Qt, QPoint, QPointF, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication([])
from canvas import PdfCanvas, A_STAMP, A_TEXT, A_HL

sample = os.path.join(OUT, "sample.pdf")
import subprocess; subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "make_sample.py"), sample], check=True)
work = os.path.join(OUT, "work.pdf")
shutil.copy(sample, work)

doc = pymupdf.open(work)
cv = PdfCanvas()
cv.author = "tester"
cv.resize(900, 900)
cv.show()
cv.set_document(doc, work)
QApplication.processEvents()
cv.fit_width()
QApplication.processEvents()


def shot(name):
    QApplication.processEvents()
    cv.viewport().grab().save(os.path.join(OUT, name + ".png"))


def px_of(pg, x, y):
    p = cv._to_px(pg, x, y)
    return QPoint(int(p.x()), int(p.y()))


def drag(a, b):
    vp = cv.viewport()
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    steps = 8
    for k in range(1, steps + 1):
        pt = QPoint(a.x() + (b.x() - a.x()) * k // steps, a.y() + (b.y() - a.y()) * k // steps)
        QTest.mouseMove(vp, pt)
        QApplication.processEvents()
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
    QApplication.processEvents()


def click(pt):
    vp = cv.viewport()
    QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
    QApplication.processEvents()


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        global failed
        failed = True


failed = False
shot("01_open")
print("zoom", round(cv.zoom, 3), "pages", cv.page_count)

# --- text selection + highlight (English line on page 1)
w = cv._get_words(0)
print("words on p1:", len(w), [x[4] for x in w[:6]])
first = next(x for x in w if x[4].startswith("agreement"))
last = next(x for x in w if x[4].startswith("parties"))
a = px_of(0, first[0] + 1, (first[1] + first[3]) / 2)
b = px_of(0, last[2] - 1, (last[1] + last[3]) / 2)
drag(a, b)
check(cv.sel_words is not None, "drag selects words")
print("selected:", repr(cv.selected_text()))
shot("02_selected")
cv.apply_markup("highlight")
check(any(x.kind == A_HL for x in cv._get_annots(0)), "highlight annotation created")
shot("03_highlighted")

# --- Hebrew selection and copy
hw = [x for x in cv._get_words(0) if any("א" <= ch <= "ת" for ch in x[4])]
print("hebrew words:", len(hw), [x[4] for x in hw[:5]])
check(len(hw) > 3, "hebrew text extracted")
a = px_of(0, hw[0][2] - 1, (hw[0][1] + hw[0][3]) / 2)
b = px_of(0, hw[4][0] + 1, (hw[4][1] + hw[4][3]) / 2)
drag(a, b)
print("selected hebrew:", repr(cv.selected_text()))
cv.apply_markup("underline")
shot("04_hebrew_underline")

# --- sticky note (Hebrew + English) via direct API then check saved content
cv._add_note_at(0, 480, 150)
QApplication.processEvents()
pop = cv._popup
check(pop is not None, "note editor opened")
pop.edit.setPlainText("שלום, זו הערה בעברית.\nAnd an English line.\nוחזרה לעברית 123")
shot("05_note_editing")
pop.finish()
QApplication.processEvents()
notes = [x for x in cv._get_annots(0) if x.kind == A_TEXT]
check(len(notes) == 1 and "בעברית" in notes[0].content, "note stored with Hebrew content")
shot("06_note_closed")

# --- text on page (Hebrew) and a date preset
cv.text_opts["size"] = 14
cv.place_text(0, 340, 676, "תל אביב, 12/11/2026 - דוד כהן")
cv.place_text(0, 60, 676, "John Smith")
shot("07_text_placed")
stamps = [x for x in cv._get_annots(0) if x.kind == A_STAMP]
check(len(stamps) == 2, "two text stamps")

# --- signature stamp from a generated PNG
from signature import render_signature_text
img = render_signature_text("David Cohen", "Segoe Script", (0.05, 0.1, 0.6))
from textrender import image_to_png
cv.pending_png = image_to_png(img)
cv.pending_img = img
cv.pending_w_pt = 140
cv.place_pending_signature(0, 160, 690)
shot("08_signature")
check(cv.sel_annot is not None, "signature selected after placing")

# --- move signature by drag, then resize with handle
pg, xref = cv.sel_annot
info = cv._annot_info(pg, xref)
c = px_of(0, (info.rect.x0 + info.rect.x1) / 2, (info.rect.y0 + info.rect.y1) / 2)
drag(c, QPoint(c.x() + 150, c.y() + 30))
info2 = cv._annot_info(pg, xref)
check(abs(info2.rect.x0 - info.rect.x0) > 20, f"signature moved ({info.rect.x0:.0f}->{info2.rect.x0:.0f})")
shot("09_moved")
br = cv._handle_rects(0, info2.rect)["br"].center().toPoint()
drag(br, QPoint(br.x() + 60, br.y() + 20))
info3 = cv._annot_info(pg, xref)
check(info3.rect.width > info2.rect.width + 10, f"signature resized ({info2.rect.width:.0f}->{info3.rect.width:.0f})")
shot("10_resized")

# --- undo / redo
n_undo = len(cv.undo_stack)
cv.undo(); cv.undo()
shot("11_after_2_undo")
cv.redo(); cv.redo()
check(cv._annot_info(pg, xref) is not None and abs(cv._annot_info(pg, xref).rect.width - info3.rect.width) < 1, "undo/redo move+resize roundtrip")

# --- delete + undo
cv.sel_annot = (pg, xref)
cv.delete_selected()
check(cv._annot_info(pg, xref) is None, "signature deleted (soft)")
cv.undo()
check(cv._annot_info(pg, xref) is not None, "delete undone")
cv.delete_selected() if cv.sel_annot else None

# --- search
cv.search("agreement")
print("search hits", len(cv._hits))
check(len(cv._hits) >= 3, "search finds English on all pages")
shot("12_search")
cv.search("הסכם")
print("hebrew search hits", len(cv._hits))

# --- save incrementally & reload
cv.purge_trashed()
doc.saveIncr()
doc.close()
d2 = pymupdf.open(work)
kinds = [(a.type[1], a.info.get("content", "")[:20]) for a in d2[0].annots()]
print("saved annots p1:", kinds)
check(len(kinds) >= 6, "annotations persisted in file")
pm = d2[0].get_pixmap(dpi=100)
pm.save(os.path.join(OUT, "13_saved_render.png"))
d2.close()
print("FAILED" if failed else "ALL OK")
