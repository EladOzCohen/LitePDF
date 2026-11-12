"""Drag across real documents: for sample text lines, drag first-word -> last-word and compare with the line's words."""
import os, sys, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import pymupdf
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
app = QApplication([])
import strings  # noqa
from canvas import PdfCanvas

path = sys.argv[1]
pages = [int(p) for p in sys.argv[2].split(",")] if len(sys.argv) > 2 else [0, 1]
doc = pymupdf.open(path)
cv = PdfCanvas(); cv.resize(1000, 900); cv.show(); cv.set_document(doc, path); cv.set_zoom(1.2)
QApplication.processEvents()
vp = cv.viewport()
print(os.path.basename(path), "pages", doc.page_count)
for pg in pages:
    cv.goto_page(pg); QApplication.processEvents()
    words = cv._get_words(pg)
    raw = doc[pg].get_text("words")
    from canvas import _stream_is_scrambled
    print(f" page {pg+1}: {len(words)} words, scrambled={_stream_is_scrambled(raw)}, blocks={len({w[5] for w in raw})}")
    # pick a few lines with >= 5 words
    rows = {}
    for k, w in enumerate(words):
        rows.setdefault((w[5], w[6]), []).append(k)
    cand = [v for v in rows.values() if len(v) >= 6]
    random.seed(1)
    for idxs in random.sample(cand, min(4, len(cand))):
        ws = [words[k] for k in idxs]
        a, b = ws[0], ws[-1]
        # visible?
        def center(w): return ((w[0]+w[2])/2, (w[1]+w[3])/2)
        def px(x, y):
            p = cv._to_px(pg, x, y); return QPoint(int(p.x()), int(p.y()))
        pa, pb = px(*center(a)), px(*center(b))
        if not (0 <= pa.y() < 900 and 0 <= pb.y() < 900):
            cv.goto_page(pg, max(0, a[1] - 100)); QApplication.processEvents()
            pa, pb = px(*center(a)), px(*center(b))
        cv.clear_selection()
        QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pa)
        for s in range(1, 11):
            QTest.mouseMove(vp, QPoint(pa.x() + (pb.x()-pa.x())*s//10, pa.y() + (pb.y()-pa.y())*s//10)); QApplication.processEvents()
        QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pb)
        sel = cv.sel_words
        n = (sel[2]-sel[1]+1) if sel else 0
        print(f"   line of {len(idxs)} words: drag selected {n} words ->", "OK" if n >= len(idxs) else "TOO FEW", "| pressed y=%d" % pa.y())
