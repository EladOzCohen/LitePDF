"""Integration: build the real MainWindow, open a PDF, exercise toolbar logic, screenshot, save, print-to-PDF."""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
OUT = sys.argv[1]
LANG = sys.argv[2] if len(sys.argv) > 2 else "he"

import pymupdf
from PySide6.QtCore import Qt, QSettings, QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

app = QApplication([])
import i18n
i18n.set_lang(LANG)
import strings  # noqa
app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if LANG == "he" else Qt.LayoutDirection.LeftToRight)
settings = QSettings(os.path.join(OUT, f"test_{LANG}.ini"), QSettings.Format.IniFormat)
settings.clear()
if LANG == "en":
    settings.setValue("dark", False)
from main_window import MainWindow

sample = os.path.join(OUT, "sample.pdf")
if not os.path.exists(sample):
    subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "make_sample.py"), sample], check=True)
work = os.path.join(OUT, f"app_work_{LANG}.pdf")
shutil.copy(sample, work)

win = MainWindow(settings)
win.show()
QApplication.processEvents()
win.grab().save(os.path.join(OUT, f"app_{LANG}_00_welcome.png"))
win.open_path(work)
QApplication.processEvents()
QTest.qWait(300)
win.toggle_sidebar()
QTest.qWait(500)
c = win.canvas
failed = False


def check(cond, msg):
    global failed
    print(("PASS " if cond else "FAIL ") + msg)
    failed = failed or not cond


check(c.doc is not None and c.page_count == 3, "document loaded")
check(win.thumbs.count() == 3, "thumbnails list has 3 items")
check(win.outline.topLevelItemCount() >= 2, "outline populated")
win.set_tool("highlight")
check(c.tool == "highlight" and win.tool_actions["highlight"].isChecked(), "highlight tool selected")

# select text then click the highlight button -> applies immediately
w = c._get_words(0)
first = next(x for x in w if x[4].startswith("payment") or x[4].startswith("Payment"))
c.set_tool("select")
c.sel_words = (0, w.index(first), w.index(first) + 3)
win._tool_clicked("highlight")
check(len([a for a in c._get_annots(0) if a.kind == 8]) == 1, "toolbar highlight applies to selection")

# text presets
c.text_opts["size"] = 14
win._pick_text_preset("date")
check(c.tool == "text" and c.text_preset == "date", "date preset armed")
pt = c._to_px(0, 400, 690)
QTest.mouseClick(c.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(pt.x()), int(pt.y())))
check(len([a for a in c._get_annots(0) if a.kind == 13]) == 1, "date stamp placed by click")

# signature via store
from signature import render_signature_text
from textrender import image_to_png
img = render_signature_text("אלעד כהן", "Segoe Script", (0.05, 0.12, 0.62))
p = win.store.add_png(image_to_png(img))
win._use_signature(p)
check(c.tool == "sign" and c.pending_img is not None, "signature armed")
pt = c._to_px(0, 150, 685)
QTest.mouseMove(c.viewport(), QPoint(int(pt.x()), int(pt.y())))
QTest.mouseClick(c.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(pt.x()), int(pt.y())))
QApplication.processEvents()
check(c.tool == "select", "tool resets to select after signing")
check(len([a for a in c._get_annots(0) if a.kind == 13]) == 2, "signature stamp placed")
win.store.delete(p)

# note
c._add_note_at(0, 500, 130)
c._popup.edit.setPlainText("בדיקה: פתק בעברית עם English באמצע")
c._popup.finish()
QApplication.processEvents()
win.sidebar.setCurrentIndex(2)
win._refresh_notes()
check(win.notes_list.count() == 1 and "בדיקה" in win.notes_list.item(0).text(), "notes panel lists the note")
win.canvas.search("agreement")
QApplication.processEvents()
win.show_search()
win.searchbar.edit.setText("agreement")
QTest.qWait(600)
check(win.searchbar.count.text().endswith("/ 3"), f"search counter: {win.searchbar.count.text()!r}")
win.grab().save(os.path.join(OUT, f"app_{LANG}_01_main.png"))
win.close_search()

# save (in place, incremental) bypassing the dialog
check(c.is_dirty, "document dirty")
ok = win._write(work)
check(ok and not c.is_dirty, "saved in place")
d = pymupdf.open(work)
n = sum(1 for _ in d[0].annots())
d.close()
check(n == 4, f"annotations persisted ({n})")

# rotate -> full save path
c.rotate_all(90)
check(c.is_dirty, "rotation marks dirty")
ok = win._write(work)
check(ok, "saved after rotation")
d = pymupdf.open(work)
check(d[0].rotation == 90 and sum(1 for _ in d[0].annots()) == 4, "rotation + annotations in file")
d.close()
c.rotate_all(-90)
win._write(work)

# dark mode screenshot
win.toggle_dark()
QTest.qWait(300)
win.grab().save(os.path.join(OUT, f"app_{LANG}_02_dark.png"))

# print to PDF through the same drawing code path
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtGui import QPainter
import printing
pr = QPrinter(QPrinter.PrinterMode.HighResolution)
pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
pr.setOutputFileName(os.path.join(OUT, f"printed_{LANG}.pdf"))
painter = QPainter(pr)
for i in range(c.page_count):
    if i:
        pr.newPage()
    printing._draw_page(painter, pr, c.doc[i], 200)
painter.end()
pd = pymupdf.open(os.path.join(OUT, f"printed_{LANG}.pdf"))
check(pd.page_count == 3, "print pipeline produced 3 pages")
pm = pd[0].get_pixmap(dpi=60)
pm.save(os.path.join(OUT, f"printed_{LANG}_p1.png"))
pd.close()

c.set_document(None, None)
print("FAILED" if failed else "ALL OK")
