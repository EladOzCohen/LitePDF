"""Hand tool: dragging over TEXT must pan the page, never select; clicks still open notes/links."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
OUT = sys.argv[1]
import pymupdf
from PySide6.QtCore import Qt, QPoint, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
app = QApplication([])
import i18n, strings  # noqa
from main_window import MainWindow
failed = False
def check(c, m):
    global failed
    print(("PASS " if c else "FAIL ") + m); failed = failed or not c
import shutil, subprocess
sample = os.path.join(OUT, "sample.pdf")
if not os.path.exists(sample):
    subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "make_sample.py"), sample], check=True)
work = os.path.join(OUT, "hand_work.pdf"); shutil.copy(sample, work)
win = MainWindow(QSettings(os.path.join(OUT, "hand.ini"), QSettings.Format.IniFormat)); win.show(); win.open_path(work)
QTest.qWait(300)
c = win.canvas; vp = c.viewport()
c.set_zoom(1.6); QTest.qWait(100)
win._tool_clicked("hand")
check(c.tool == "hand" and win.tool_actions["hand"].isChecked(), "hand tool selectable from toolbar action")
w = [x for x in c._get_words(0) if x[4].startswith("agreement")][0]
p = c._to_px(0, (w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
a = QPoint(int(p.x()), int(p.y())); b = QPoint(a.x() - 60, a.y() - 90)
v0, h0 = c.verticalScrollBar().value(), c.horizontalScrollBar().value()
check(c._word_near(0, (w[0] + w[2]) / 2, (w[1] + w[3]) / 2, 1) is not None, "pressing on real text")
QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
for k in range(1, 9):
    QTest.mouseMove(vp, QPoint(a.x() + (b.x() - a.x()) * k // 8, a.y() + (b.y() - a.y()) * k // 8)); QApplication.processEvents()
QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
check(c.sel_words is None, "hand drag over text does NOT select it")
check(c.verticalScrollBar().value() > v0 + 60, f"page panned (v {v0} -> {c.verticalScrollBar().value()})")
# sticky note click still works
c._add_note_at(0, 480, 600); c._popup.edit.setPlainText("hello"); c._popup.finish(); QApplication.processEvents()
note = [x for x in c._get_annots(0) if x.kind == 0][0]
c.goto_page(0); QApplication.processEvents()
pn = c._to_px(0, (note.rect.x0 + note.rect.x1) / 2, (note.rect.y0 + note.rect.y1) / 2)
QTest.mouseClick(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(pn.x()), int(pn.y())))
QApplication.processEvents()
check(c._popup is not None, "click on a note with the hand tool opens it")
c._popup.finish()
win.grab().save(os.path.join(OUT, "toolbar_hand.png"))
print("FAILED" if failed else "ALL OK")
