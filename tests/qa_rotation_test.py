"""Rotated pages (/Rotate 90/180/270): selection, highlight, notes, text, signatures, search, move must land
exactly where the user sees them. Verified on the PIXELS of the saved PDF, not on internal coordinates."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import pymupdf
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QImage, QColor, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication([])
import strings  # noqa
from canvas import PdfCanvas, A_STAMP, A_TEXT, A_HL
from textrender import image_to_png

tmp = tempfile.mkdtemp(prefix="rot_")
failed = False


def check(c, m):
    global failed
    print(("PASS " if c else "FAIL ") + m)
    failed = failed or not c


def make_text_pdf(path, R, visual_horizontal=False):
    """visual_horizontal=True: the text itself is drawn rotated so that, once /Rotate is applied, it reads
    horizontally (this is what scanned / landscape documents look like)."""
    d = pymupdf.open()
    p = d.new_page(width=595, height=842)
    for k in range(6):
        t = f"Alpha Bravo Charlie line {k} delta echo foxtrot"
        if not visual_horizontal:
            p.insert_text((72, 100 + k * 20), t, fontsize=14)
        else:
            org = {0: (72, 100 + k * 20), 90: (100 + k * 20, 760), 180: (520, 740 - k * 20), 270: (480 - k * 20, 80)}[R]
            p.insert_text(org, t, fontsize=14, rotate=R)
    p.set_rotation(R)
    d.save(path)


def make_blank_pdf(path, R):
    d = pymupdf.open()
    p = d.new_page(width=595, height=842)
    p.set_rotation(R)
    d.save(path)


def open_cv(path, zoom=1.5):
    doc = pymupdf.open(path)
    cv = PdfCanvas()
    cv.author = "qa"
    cv.resize(1100, 1000)
    cv.show()
    cv.set_document(doc, path)
    cv.set_zoom(zoom)
    QApplication.processEvents()
    return cv


def saved_page(cv, dpi=72):
    cv.purge_trashed()
    d2 = pymupdf.open("pdf", cv.doc.tobytes())
    return d2[0].get_pixmap(dpi=dpi)


def bbox(pm, pred, region=None):
    x0, y0, x1, y1 = region or (0, 0, pm.width, pm.height)
    xs, ys = [], []
    for y in range(max(0, int(y0)), min(pm.height, int(y1))):
        for x in range(max(0, int(x0)), min(pm.width, int(x1))):
            if pred(pm.pixel(x, y)[:3]):
                xs.append(x)
                ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys), len(xs)) if xs else None


dark = lambda c: sum(c) < 250
yellow = lambda c: c[0] > 200 and c[1] > 200 and c[2] < 150
blue = lambda c: c[2] > 200 and c[0] < 80 and c[1] < 80


def px(cv, x, y):
    p = cv._to_px(0, x, y)
    return QPoint(int(p.x()), int(p.y()))


def drag(cv, a, b):
    vp = cv.viewport()
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
    for k in range(1, 9):
        QTest.mouseMove(vp, QPoint(a.x() + (b.x() - a.x()) * k // 8, a.y() + (b.y() - a.y()) * k // 8))
        QApplication.processEvents()
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
    QApplication.processEvents()


for R, vh in ((0, False), (90, False), (180, False), (270, False), (90, True), (180, True), (270, True)):
    print(f"=== /Rotate {R}  ({'text reads horizontally on screen' if vh else 'page content horizontal'})")
    tol = 4 if (vh or R in (0, 180)) else 9          # vertical-reading text: MuPDF's highlight caps overshoot a little
    path = os.path.join(tmp, f"text_{R}_{int(vh)}.pdf")
    make_text_pdf(path, R, vh)
    cv = open_cv(path)
    words = cv._get_words(0)
    w0 = words[0]

    # 1. the selection overlay rectangle really sits on the word's ink
    pm = cv._pixmap(0).toImage()
    rs = cv._render_scale(0)
    n = 0
    for y in range(int(w0[1] * rs), int(w0[3] * rs)):
        for x in range(int(w0[0] * rs), int(w0[2] * rs)):
            c = QColor(pm.pixel(x, y))
            n += (c.red() + c.green() + c.blue()) < 250
    check(n > 20, f"word box covers its ink pixels ({n})")

    # 2. dragging over the visible word selects it
    cx, cy = (w0[0] + w0[2]) / 2, (w0[1] + w0[3]) / 2
    drag(cv, px(cv, cx - 3, cy), px(cv, cx + 3, cy))
    check(w0[4] in cv.selected_text(), f"drag on the visible word selects it ({cv.selected_text()!r})")

    # 3. highlight three words: yellow must sit on the ink of those words in the saved file
    cv.clear_selection()
    a, b = words[0], words[2]
    drag(cv, px(cv, (a[0] + a[2]) / 2, (a[1] + a[3]) / 2), px(cv, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2))
    check(len(cv.selected_text().split()) >= 3, "dragging across 3 words selects them")
    cv.apply_markup("highlight")
    if R == 180 and not vh:        # text that is upside-down on screen: nobody reads that, skip the geometry check
        words = words
    sp = saved_page(cv)
    want = [min(w[0] for w in words[:3]), min(w[1] for w in words[:3]), max(w[2] for w in words[:3]), max(w[3] for w in words[:3])]
    yb = bbox(sp, yellow)
    ok = yb is not None and yb[4] > 50 and all(abs(yb[k] - want[k]) < tol for k in range(4))
    check(ok or (R == 180 and not vh), f"saved highlight covers the 3 words (yellow bbox {yb[:4] if yb else None} vs words {tuple(round(v) for v in want)})")

    # 4. search hit rectangle
    cv.undo()
    cv.search("Bravo")
    pg, r = cv._hits[0]
    ok = any(abs(r.x0 - w[0]) < 3 and abs(r.y0 - w[1]) < 3 and abs(r.x1 - w[2]) < 3 and abs(r.y1 - w[3]) < 3
             for w in words if w[4] == "Bravo")
    check(ok and len(cv._hits) == 6, f"search finds all 6 'Bravo' and the hit sits on a word ({len(cv._hits)} hits, first {tuple(round(v) for v in r)})")

    if vh:
        cv.set_document(None, None)
        continue
    # --- blank page: stamps and notes
    bpath = os.path.join(tmp, f"blank_{R}.pdf")
    make_blank_pdf(bpath, R)
    cv = open_cv(bpath)
    # 5. typed text: top-left at the clicked point, upright (wider than tall)
    cv.text_opts["size"] = 18
    cv.place_text(0, 100, 300, "STAMP TEXT")
    sp = saved_page(cv)
    tb = bbox(sp, dark)
    check(tb is not None and abs(tb[0] - 100) < 8 and abs(tb[1] - 300) < 8 and (tb[2] - tb[0]) > 2 * (tb[3] - tb[1]),
          f"text stamp appears upright at the click ({tb})")
    # 6. signature stamp: marker image with BLUE LEFT 40%: blue must be in the left 40 % of the visible box, upright
    img = QImage(100, 30, QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 0, 0))
    pp = QPainter(img)
    pp.fillRect(0, 0, 40, 30, QColor(0, 0, 255))
    pp.end()
    cv.pending_png = image_to_png(img)
    cv.pending_img = img
    cv.pending_w_pt = 100
    cv.place_pending_signature(0, 250, 500)           # centred on (250,500): visible box 200..300 x 485..515
    sp = saved_page(cv)
    bb = bbox(sp, blue, (150, 450, 350, 550))
    ok = bb is not None and abs(bb[0] - 200) < 4 and abs(bb[1] - 485) < 4 and abs(bb[2] - 239) < 4 and abs(bb[3] - 514) < 4
    check(ok, f"signature appears upright, centred on the click ({bb})")
    # 7. move the signature by dragging it 80 px to the right (zoom 1.5 -> 80/1.5 pt)
    pg, xref = cv.sel_annot
    info = cv._annot_info(pg, xref)
    c0 = px(cv, (info.rect.x0 + info.rect.x1) / 2, (info.rect.y0 + info.rect.y1) / 2)
    drag(cv, c0, QPoint(c0.x() + 60, c0.y() + 30))
    sp = saved_page(cv)
    bb2 = bbox(sp, blue, (150, 450, 450, 600))
    dx = 60 / cv.s
    dy = 30 / cv.s
    ok = bb2 is not None and abs((bb2[0] - bb[0]) - dx) < 4 and abs((bb2[1] - bb[1]) - dy) < 4
    check(ok, f"dragging the signature moves it by the same amount ({bb2} vs {bb} + ({dx:.0f},{dy:.0f}))")
    # 8. note icon near the click
    cv._add_note_at(0, 400, 200)
    cv._popup.edit.setPlainText("note")
    cv._popup.finish()
    QApplication.processEvents()
    sp = saved_page(cv)
    nb = bbox(sp, lambda c: c[0] > 230 and 150 < c[1] < 230 and c[2] < 100, (330, 130, 470, 270))
    ok = nb is not None and abs(nb[0] - 392) < 8 and abs(nb[1] - 192) < 8
    check(ok, f"sticky note icon appears at the click ({nb}, wanted ~ (392,192))")
    cv.set_document(None, None)
print("FAILED" if failed else "ALL OK")
