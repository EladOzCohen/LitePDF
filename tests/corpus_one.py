"""Process ONE real PDF end-to-end on a COPY: open, select, highlight, note, text, signature, save, reopen, verify. Prints one JSON line."""
import json, os, shutil, sys, time, tempfile, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
src = sys.argv[1]
res = {"file": os.path.basename(src), "kb": os.path.getsize(src) // 1024, "errors": [], "notes": []}
try:
    import pymupdf
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    import strings  # noqa
    from canvas import PdfCanvas, reading_order, _stream_is_scrambled
    tmp = tempfile.mkdtemp(prefix="corpus_")
    work = os.path.join(tmp, "work.pdf"); shutil.copy(src, work)
    t0 = time.time()
    doc = pymupdf.open(work)
    res["needs_pass"] = bool(doc.needs_pass)
    if doc.needs_pass:
        res["notes"].append("password protected - skipped"); print(json.dumps(res, ensure_ascii=False)); sys.exit(0)
    res["pages"] = doc.page_count
    res["repaired"] = bool(doc.is_repaired)
    res["rotations"] = sorted({doc[i].rotation for i in range(min(doc.page_count, 30))})
    cv = PdfCanvas(); cv.author = "qa"; cv.resize(1000, 900); cv.show()
    cv.set_document(doc, work); cv.set_zoom(1.2); QApplication.processEvents()
    res["open_s"] = round(time.time() - t0, 2)
    # find first page with a decent amount of text
    pg = None
    for i in range(min(doc.page_count, 40)):
        t1 = time.time(); w = cv._get_words(i); dt = time.time() - t1
        res["max_words_s"] = round(max(res.get("max_words_s", 0), dt), 3)
        if len(w) >= 40 and pg is None:
            pg = i
    res["text_page"] = pg
    if pg is None:
        res["notes"].append("no text page in first 40 pages (scan?)")
        pg = 0
    cv.goto_page(pg); QApplication.processEvents()
    words = cv._get_words(pg)
    res["words_on_page"] = len(words)
    res["scrambled"] = _stream_is_scrambled(doc[pg].get_text("words"))
    vp = cv.viewport()
    def px(x, y):
        p = cv._to_px(pg, x, y); return QPoint(int(p.x()), int(p.y()))
    def drag(a, b):
        QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a)
        for k in range(1, 11):
            QTest.mouseMove(vp, QPoint(a.x() + (b.x() - a.x()) * k // 10, a.y() + (b.y() - a.y()) * k // 10)); QApplication.processEvents()
        QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b)
        QApplication.processEvents()
    checks = []
    if words:
        rows = {}
        for k, w in enumerate(words): rows.setdefault((w[5], w[6]), []).append(k)
        def visible(v):
            y = cv._to_px(pg, 0, words[v[0]][1]).y(); return 40 < y < cv.viewport().height() - 40
        cand = [v for v in rows.values() if len(v) >= 5]
        vis = [v for v in cand if visible(v)] or cand
        if vis:
            line = vis[len(vis) // 2]
            a, b = words[line[0]], words[line[-1]]
            if not visible(line):
                cv.goto_page(pg, max(0, a[1] - 120)); QApplication.processEvents()
            cv.set_tool("highlight")
            drag(px((a[0] + a[2]) / 2, (a[1] + a[3]) / 2), px((b[0] + b[2]) / 2, (b[1] + b[3]) / 2))
            hl = [x for x in cv._get_annots(pg) if x.kind == 8]
            span = max(words[k][2] for k in line) - min(words[k][0] for k in line)
            ok = bool(hl) and hl[-1].quads and max(q.width for q in hl[-1].quads) > 0.9 * span
            checks.append(("drag-highlight-whole-line", bool(ok)))
            cv.set_tool("select")
    # note / text stamp / signature stamp on this page
    cv._add_note_at(pg, 100, 100)
    if cv._popup is not None:
        cv._popup.edit.setPlainText("הערת בדיקה QA note"); cv._popup.finish(); QApplication.processEvents()
    cv.text_opts["size"] = 12
    cv.place_text(pg, 120, 160, "טקסט בדיקה QA text")
    from signature import render_signature_text
    from textrender import image_to_png
    img = render_signature_text("QA Test", "Segoe Script")
    cv.pending_png = image_to_png(img); cv.pending_img = img; cv.pending_w_pt = 120
    cv.place_pending_signature(pg, 200, 260)
    n_before = len([a for a in cv._get_annots(pg)])
    cv.undo(); cv.undo(); cv.redo(); cv.redo()
    checks.append(("undo-redo-consistent", len(cv._get_annots(pg)) == n_before))
    cv.rotate_all(90); cv.rotate_all(-90)
    cv.fit_page(); cv.fit_width(); cv.goto_page(doc.page_count - 1); QApplication.processEvents()
    if words:
        cv.search(words[len(words) // 2][4][:6]); checks.append(("search-finds", len(cv._hits) >= 1))
    # save incrementally if possible else full, reopen, verify
    cv.purge_trashed()
    expect = {p: len(cv._get_annots(p)) for p in [pg]}
    if doc.can_save_incrementally():
        doc.saveIncr(); res["save"] = "incremental"
    else:
        out = os.path.join(tmp, "full.pdf"); doc.save(out, garbage=1, deflate=True, encryption=pymupdf.PDF_ENCRYPT_KEEP); res["save"] = "full"
        work = out
    doc.close()
    d2 = pymupdf.open(work)
    got = len([a for a in d2[pg].annots() if a.type[0] != 16])
    checks.append(("roundtrip-annot-count", got == expect[pg]))
    pm = d2[pg].get_pixmap(dpi=60); checks.append(("saved-page-renders", pm.width > 0))
    res["annots_after"] = got
    d2.close()
    res["checks"] = checks
    res["failed_checks"] = [c for c, ok in checks if not ok]
    cv.set_document(None, None)
except SystemExit:
    pass
except Exception:
    res["errors"].append(traceback.format_exc()[-600:])
print(json.dumps(res, ensure_ascii=False))
