"""Text selection must follow what is on screen, not the PDF's internal stream order."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
OUT = sys.argv[1]
import pymupdf
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication([])
import strings  # noqa
from canvas import PdfCanvas

failed = False


def check(cond, msg):
    global failed
    print(("PASS " if cond else "FAIL ") + msg)
    failed = failed or not cond


import subprocess
hard = os.path.join(OUT, "hard.pdf")
subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "make_hard_sample.py"), hard], check=True)
doc = pymupdf.open(hard)
cv = PdfCanvas()
cv.resize(900, 900)
cv.show()
cv.set_document(doc, hard)
cv.set_zoom(1.3)
QApplication.processEvents()
vp = cv.viewport()


def center(w):
    return (w[0] + w[2]) / 2, (w[1] + w[3]) / 2


def px(x, y):
    p = cv._to_px(0, x, y)
    return QPoint(int(p.x()), int(p.y()))


def drag(a, b):
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    for k in range(1, 9):
        QTest.mouseMove(vp, QPoint(a.x() + (b.x() - a.x()) * k // 8, a.y() + (b.y() - a.y()) * k // 8))
        QApplication.processEvents()
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
    QApplication.processEvents()


def find(text, y_min=0, y_max=9999):
    for w in cv._get_words(0):
        if w[4] == text and y_min <= w[1] <= y_max:
            return w
    raise KeyError(text)


# --- English paragraph with scrambled stream: drag from 'quick' (line 1) to 'field' (line 2/3)
a, b = find("quick", 0, 300), find("field", 0, 300)
# geometric truth: words from 'quick' to 'field' in visual reading order
visual = sorted((w for w in doc[0].get_text("words") if w[1] < 250), key=lambda w: (round(w[1] / 10), w[0]))
names = [w[4] for w in visual]
want = names[names.index("quick"):names.index("field") + 1]
cv.set_tool("select")
drag(px(*center(a)), px(*center(b)))
got = cv.selected_text().replace("\n", " ").split()
print("want:", " ".join(want))
print("got: ", " ".join(got))
check(got == want, "English sentence across lines selects every word between, in reading order")

# --- start the drag in the blank margin left of the line (a few pt before the word)
a2 = find("The", 0, 300)
cv.clear_selection()
drag(px(a2[0] - 12, center(a2)[1]), px(*center(b)))
got2 = cv.selected_text().replace("\n", " ").split()
check(len(got2) >= len(want) and got2[0] == "The", "drag that starts in the margin before the line still selects text")

# --- highlight tool end-to-end on the scrambled page
cv.clear_selection()
cv.set_tool("highlight")
drag(px(*center(a)), px(*center(b)))
n = [x for x in cv._get_annots(0) if x.kind == 8]
check(len(n) == 1 and len(n[0].quads) >= 2, f"highlight tool spans multiple lines in one drag (quads={len(n[0].quads) if n else 0})")

# --- Hebrew paragraph (each word its own object, scrambled stream): drag right->left across lines
heb = [w for w in doc[0].get_text("words") if w[1] > 280]
rows = sorted({round(w[1] / 8) for w in heb})
def row_of(w): return rows.index(round(w[1] / 8))
visual_rtl = sorted(heb, key=lambda w: (row_of(w), -(w[0] + w[2]) / 2))
names = [w[4] for w in visual_rtl]
start, end = visual_rtl[0], visual_rtl[-3]
cv.set_tool("select")
cv.clear_selection()
drag(px(*center(start)), px(*center(end)))
got = cv.selected_text().split()
want = names[:len(names) - 2]
check(got == want, f"Hebrew selection follows right-to-left reading order across lines ({len(got)}/{len(want)} words)")
check(len(got) >= 15, "Hebrew selection spans several lines")
print("FAILED" if failed else "ALL OK")
