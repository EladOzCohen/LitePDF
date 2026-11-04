# LitePDF — project notes for Claude

Light PDF reader for Windows that replaces Adobe Reader for the user's needs: **RTL-correct sticky notes,
highlighting, signing, printing**. Python 3.13 (standalone install) + PySide6 + PyMuPDF. Started 2026-11-04.

Run: double-click `LitePDF.lnk` (or `LitePDF.pyw`), or
`pythonw.exe LitePDF.pyw [file.pdf]` (standalone Python 3.13 under `%LOCALAPPDATA%\Programs\Python`).
Recreate the shortcut/icon with `powershell -File tools\make_shortcut.ps1`.

**EXE (built 2026-11-04):** `dist\LitePDF\LitePDF.exe` (onedir, ~145 MB, starts in ~1.7 s, ~130 MB RAM). Rebuild with
`powershell -File tools\build_exe.ps1` (PyInstaller; script also trims opengl32sw/Qt Quick/Qml/Pdf DLLs). The whole `dist\LitePDF` folder must stay together.
`build\` and `dist\` are generated — don't edit. Registered for the current user (HKCU only) on 2026-11-04 with `tools\register_default_app.ps1` (undo: `tools\unregister_default_app.ps1`; rerun if the dist folder moves).
Windows blocks silent default-app changes: the user must pick LitePDF once in Settings > Default apps > .pdf (UserChoice was still Acrobat.Document.DC after registering).

## User decisions (asked 2026-11-04)
- Notes/markup are stored **inside the PDF** as standard annotations (Highlight/Underline/StrikeOut/Text/Stamp).
- Save: first Ctrl+S per opened file asks "overwrite original / save a new copy"; later saves are silent.
- Signatures: **draw (mouse/pen/touch)** and **type name in handwriting font**; saved library in
  `%APPDATA%\LitePDF\signatures\*.png`, placed with one click, then drag/resize. NOT cryptographic signing (user declined certificates and image import).
- UI language Hebrew/English with a switch (menu ≡ > Language; restarts the app). Hebrew = app-wide RTL layout, PDF canvas always LTR.
- Extras chosen: search + thumbnails (also Contents + Notes panel), free text on page, dark mode, remember last page / recent files.

## Layout
- `src/canvas.py` — `PdfCanvas` (QAbstractScrollArea): lazy page rendering + cache, text selection via `get_text("words")`,
  all tools, undo/redo, popups, search. Biggest file.
- `src/main_window.py` — toolbars, sidebar, search bar, open/save/print, settings (QSettings "LitePDF"), theme.
- `src/popups.py` — note editor + inline text input (per-paragraph auto direction: `QTextOption.setTextDirection(LayoutDirectionAuto)`).
- `src/textrender.py` — QTextDocument → transparent PNG (bidi-aware); used for text stamps and typed signatures.
- `src/signature.py`, `src/printing.py`, `src/delegates.py`, `src/icons.py` (inline SVG icons + app icon drawn in code), `src/i18n.py` + `src/strings.py`.
- `tests/` — `canvas_test.py`, `app_test.py <outdir> he|en`, `interaction_test.py <outdir>`; run with `python -X utf8 tests\x.py <scratch dir>`.

## Design facts / pitfalls (learned the hard way)
- Typed text + signatures are **image Stamp annotations** (Hebrew shaping/bidi can't be done by MuPDF FreeText).
  The source string is kept in the stamp's /Contents and `subject = "litepdf-text|size|r,g,b"` so double-click re-edits it.
- Delete is **soft**: annotation gets the Hidden flag (`trashed` set); `purge_trashed()` really deletes before saving. Undo = unhide.
- **Always reopen the document after saving** (`MainWindow._write`). After `saveIncr()` PyMuPDF's in-memory doc goes stale:
  a later rotate + save silently dropped annotations.
- `Annot` objects die when their `Page` is garbage-collected → canvas keeps a `_page()` cache; never use `self.doc[i]` for mutations.
- Qt 6.11 follows Windows dark mode by default; `apply_theme` forces the scheme + explicit palettes. Default = follow system on first run.
- Qt `offscreen` platform has no fonts on Windows (renders boxes) — run UI tests on the normal platform.
- Console is cp1252: run scripts with `python -X utf8` when printing Hebrew.
- Printing renders pages with PyMuPDF at ≤300 dpi (annotations included) and draws them via QPrinter; landscape pages auto-rotate; shrinks only if the page doesn't fit.

## Not done / ideas
- Not verified: how Adobe displays Hebrew inside *its* sticky-note popup (user may see LTR alignment there; our own editor is correct). Interactive print dialog with a physical printer not tried (render pipeline tested via PDF output).
- AcroForm widgets (real form fields) are displayed but not fillable — use the Text tool.
- Possible next: PyInstaller exe + "Open with / default app" registration, freehand ink tool, shapes, multi-document tabs, copy-to-clipboard of selected area as image.
