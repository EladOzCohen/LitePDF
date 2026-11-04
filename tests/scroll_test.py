"""Mouse-wheel scrolling must glide (many small steps) and land exactly where the notches say."""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
OUT = sys.argv[1]
import pymupdf
from PySide6.QtCore import Qt, QPointF, QPoint
from PySide6.QtGui import QWheelEvent
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


big = os.path.join(OUT, "scroll_big.pdf")
d = pymupdf.open()
for i in range(40):
    p = d.new_page()
    for k in range(45):
        p.insert_text((72, 90 + k * 15), f"Page {i + 1} line {k} " + "lorem ipsum dolor sit amet " * 3, fontsize=10)
d.save(big)
d.close()
cv = PdfCanvas()
cv.resize(900, 800)
cv.show()
cv.set_document(pymupdf.open(big), big)
cv.set_zoom(1.0)
QApplication.processEvents()
vb = cv.verticalScrollBar()
vp = cv.viewport()


def wheel(delta_y):
    ev = QWheelEvent(QPointF(300, 300), QPointF(300, 300), QPoint(0, 0), QPoint(0, delta_y),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    app.sendEvent(vp, ev)


start = vb.value()
samples = []
for _ in range(3):                      # three quick notches (like a fast flick)
    wheel(-120)
    for _ in range(3):                  # sample every ~7 ms, also while notches arrive
        QTest.qWait(7)
        samples.append(vb.value())
t0 = time.time()
while time.time() - t0 < 0.7:
    QTest.qWait(8)
    samples.append(vb.value())
vals = [start] + samples
steps = [b - a for a, b in zip(vals, vals[1:]) if b != a]
print("start", start, "end", vb.value(), "distinct", len(set(vals)), "max step", max(steps), "min step", min(steps))
check(vb.value() - start == 330, f"3 notches land exactly 330 px lower (got {vb.value() - start})")
check(all(s > 0 for s in steps), "motion is monotonic (no jitter backwards)")
check(len(set(vals)) > 25, f"scroll glides over many frames ({len(set(vals))} distinct positions)")
check(max(steps) < 70, f"no big jumps (largest single step {max(steps)} px)")

# scrolling back up, and bumping the end of the document
for _ in range(10):
    wheel(120)
QTest.qWait(600)
check(vb.value() == 0, "wheel up past the top stops at 0")
# keyboard
cv.setFocus()
QTest.keyClick(cv, Qt.Key.Key_PageDown)
QTest.qWait(500)
check(vb.value() > 500, f"PageDown glides one screen ({vb.value()})")
# dragging the scrollbar cancels the animation
wheel(-120)
QTest.qWait(30)
vb.setValue(2000)
QTest.qWait(300)
check(vb.value() == 2000, "grabbing the scrollbar cancels the glide")
print("FAILED" if failed else "ALL OK")
