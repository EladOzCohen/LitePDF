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

## Session 2 (user feedback after real use)
- Marker only worked word-by-word: selection used PyMuPDF's internal word order, which is scrambled/visual in many PDFs (Word, Hebrew).
  Fixed with `reading_order()` in canvas.py (geometric rows; RTL rows right-to-left; falls back to page-wide rows when the stream jumps around).
  Drag may also start in the margin of a line (`_word_start`). Tests: `tests/selection_test.py` + `make_hard_sample.py`.
- Smooth scrolling: wheel/keys glide via `smooth_scroll_by` (exponential ease, ~110 px per notch); touchpads use pixel deltas. `tests/scroll_test.py`.
- Repo is PUBLIC: keep personal data out (no absolute user paths); commit with the GitHub no-reply email (repo-local `git config user.email`).

## Session 3 — the REAL marker bug
- User still saw "marker only highlights single words" after session 2. Cause: `_selection_rects` did `r |= Rect(...)` — `pymupdf.Rect` has
  no in-place union, so it only rebound a local and every row's highlight kept just the FIRST word's width. Selection itself was fine
  (sel_words covered the whole line). Fixed by building the union explicitly.
- Lesson: tests must assert *geometry* (rect widths), not just counts. `tests/selection_test.py` now checks the highlight spans the line.
- `tests/win32_drag.py <pdf> highlight` posts real WM_LBUTTONDOWN/MOUSEMOVE/UP to the window (no cursor hijack) — use it to reproduce
  mouse bugs on real PDFs; `tests/real_pdf_drag.py` checks selection counts on real documents.
- Tests need a scratch dir argument that exists (use `mktemp -d`).

## Session 4 — full QA audit (4 parallel reviewers + corpus run on ~1,850 of the user's PDFs + fuzzing)
Hand tool added (P): drag always pans, even over text; click still opens notes/links.
Fixed (each has a regression test in `tests/qa_regression_test.py` / `qa_rotation_test.py` / `signature_ui_test.py`):
- **Signature dialog crashed on open** (`DrawPad.width` attribute shadowed `QWidget.width()`) and the **Sign dropdown was empty**
  (`QMenu.setIconSize` doesn't exist) -> signing was completely broken. Now `pen_w`, and `QWidgetAction` previews.
- **Rotated pages** (/Rotate, or the Rotate button): PyMuPDF gives words/annots/links/search hits in the UNROTATED frame; canvas now converts at the
  boundary (`_vis_rect`, `_unrot_rect`, `_unrot_quad`, `_unrot_point`). Stamps are pre-rotated by -rot so they look upright; note icons are NoRotate
  (pinned top-left corner -> map the POINT, not the rect). Quads keep visual corner order. Verified on pixels of the saved PDF.
- **Save path** (`MainWindow._write`): never loses work. Live doc stays open+dirty on any failure; full rewrite only to temp then `os.replace`
  (with retries; releases cached Page objects first); if replace fails we continue from the temp copy in memory (such a doc claims
  `can_save_incrementally()` but can't -> also require a real file). Deleted notes/signatures force a full rewrite (privacy: otherwise old bytes
  stay in the incremental revision). Signed PDFs: warn before a rewrite. Stamp image streams are compressed after creation (+130 KB -> +5 KB).
  Popups/drags are committed/cancelled (`canvas.commit_pending()`) before save/open/close/print/language switch.
- Undo/dirty: dirty = undo-stack top != top at last save (undo back to saved state = clean). Delete/undo during a stamp drag cancels the drag.
- Selection/UX: right-click elsewhere drops stale text selection; arrows only nudge stamps/notes; resize clamped to page; autoscroll while
  selecting; drag into next page selects to end of page; only the button that started a drag can end it; hand tool never resizes/selects;
  window resize keeps the page; links: only http/https/mailto are opened (PDFs are untrusted); search ignores NUL/whitespace, merges
  split hits only when boxes > real occurrences; popups close when their anchor scrolls away; huge text/size bounded (was 27 s).
- UI: Esc closes search, F3 reopens the bar, zoom box rejects junk, focus returns to page after Enter in spin/zoom, language menu exclusive,
  text preset no longer sticks, thumbnails rebuild after rotate/invert, notes list relayouts, min width 900, strings fixed.
Corpus findings that are NOT app bugs: PDFs with broken font encodings (garbage text, search can't match), 0-page/corrupt files (app shows a message).
Testing lessons: assert geometry on rendered pixels; PySide `QMenu.exec` can't be monkeypatched (use a fake menu class in the canvas module);
PyMuPDF `Rect |=` has no in-place union; scratch dirs for tests must exist.

## Installer (session 5)
`installer\LitePDF.iss` (Inno Setup 6, UTF-8 **with BOM** - build_installer.ps1 adds it) -> `installer\Output\LitePDF-Setup-1.0.0.exe` (~35 MB, lzma2).
Build: `powershell -File tools\build_installer.ps1 [-Rebuild]` (builds the exe if dist\ is missing, draws wizard art into installer\art via Qt, compiles).
- The app is **self-contained** (PyInstaller bundles python313.dll, Qt, PyMuPDF, vcruntime/msvcp/ucrt): verified by running with a stripped PATH and
  listing loaded DLLs (0 outside the app folder / Windows). So the installer installs NO Python/libraries; it only enforces Windows 10 1809+ x64 (`MinVersion`, `ArchitecturesAllowed`).
  build_exe.ps1 excludes pandas/jedi/zmq/IPython/... (they sneaked in from the global Python): bundle 145 -> 114 MB.
- Per-user (`PrivilegesRequired=lowest`, HKA = HKCU, {autopf} = %LOCALAPPDATA%\Programs), no UAC. `PrivilegesRequiredOverridesAllowed=commandline` lets IT use `/ALLUSERS`.
- English + Hebrew wizard (RTL) picked from the Windows UI language; tasks: desktop icon, "Open with" registration (same keys as tools
egister_default_app.ps1;
  all removed on uninstall); finish page: launch app / open Windows Default-apps page. Uninstall asks whether to also delete %APPDATA%\LitePDF (signatures, settings); default = keep.
- Fixed AppId GUID => installing a newer version upgrades in place (Restart Manager closes a running LitePDF, which asks to save). Unsigned => SmartScreen warning on first run.
- Testing without touching the real setup: compile a variant with `/DAppName="LitePDF Test" /DAppExe=LitePDFTest.exe /DProgId=LitePDFTest.Document /DCapKey=...LitePDFTest... /DRegAppName=LitePDFTest /DAppId={{<other guid>}`
  then silent install (`/VERYSILENT /DIR=... /TASKS=desktopicon,openwith`), verify, upgrade, uninstall. NEVER run the production Setup.exe from automation:
  it really installs (a wizard that is opened can be clicked through by whoever is at the PC, and killing Setup.exe leaves its `.tmp` child running).
- Inno gotchas: `ValueType: none` writes nothing (use string ""); define AppId as `"{{GUID}"` and use `AppId={#AppId}`.

## Not done / ideas
- Not verified: how Adobe displays Hebrew inside *its* sticky-note popup (user may see LTR alignment there; our own editor is correct). Interactive print dialog with a physical printer not tried (render pipeline tested via PDF output).
- AcroForm widgets (real form fields) are displayed but not fillable — use the Text tool.
- Possible next: PyInstaller exe + "Open with / default app" registration, freehand ink tool, shapes, multi-document tabs, copy-to-clipboard of selected area as image.
