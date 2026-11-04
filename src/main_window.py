"""Main window: toolbars, sidebar (pages / contents / notes), search bar, save / print / open logic."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pymupdf
from PySide6.QtCore import (Qt, QSize, QTimer, QSettings, QPoint, QProcess, QUrl, QDate)
from PySide6.QtGui import (QAction, QActionGroup, QColor, QIcon, QImage, QKeySequence, QPainter,
                           QPixmap, QShortcut, QPalette, QFont)
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QToolButton,
                               QStackedWidget, QSplitter, QTabWidget, QListWidget, QListWidgetItem,
                               QTreeWidget, QTreeWidgetItem, QLabel, QPushButton, QLineEdit, QSpinBox,
                               QComboBox, QMenu, QFileDialog, QMessageBox, QInputDialog, QFrame,
                               QApplication, QStatusBar, QSizePolicy)

import i18n
import icons
import printing
from canvas import PdfCanvas, HL_COLORS, A_TEXT, MARKUP, MARKUP_TOOLS
from i18n import T
from signature import SignatureStore, SignatureDialog
from delegates import AutoDirDelegate, NoteDelegate, HEAD_ROLE

APP_NAME = "LitePDF"
ZOOM_STEPS = [50, 75, 100, 125, 150, 200, 300, 400]
TEXT_COLORS = [("ink_black", (0, 0, 0)), ("ink_blue", (20, 40, 160)), ("ink_red", (200, 20, 20))]
TEXT_SIZES = [10, 12, 14, 18, 24]


def script_path() -> str:
    return os.path.abspath(sys.argv[0])


class SearchBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 6, 3)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(T("search_placeholder"))
        self.edit.setClearButtonEnabled(True)
        self.edit.setMinimumWidth(240)
        self.prev = QToolButton()
        self.next = QToolButton()
        self.count = QLabel("")
        self.close_btn = QToolButton()
        lay.addWidget(self.edit)
        lay.addWidget(self.prev)
        lay.addWidget(self.next)
        lay.addWidget(self.count)
        lay.addStretch(1)
        lay.addWidget(self.close_btn)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

    def set_icons(self, color):
        self.prev.setIcon(icons.icon("up", color))
        self.next.setIcon(icons.icon("down", color))
        self.close_btn.setIcon(icons.icon("close", color))
        self.prev.setToolTip(T("find_prev") + "  (Shift+Enter)")
        self.next.setToolTip(T("find_next") + "  (Enter)")


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        saved_dark = settings.value("dark", None)
        if saved_dark is None:      # first run: follow the Windows light/dark setting
            self.dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        else:
            self.dark = str(saved_dark).lower() == "true"
        self.invert = settings.value("invert", False, type=bool)
        self.store = SignatureStore()
        self.last_sig: Path | None = None
        self._overwrite_ok = False
        self._password: str | None = None
        self._force_close = False
        self._zoom_guard = False
        self._thumb_done: set[int] = set()
        self._notes_stale = True
        self.tool_actions: dict[str, QAction] = {}
        self._icon_actions: list[tuple[QAction | QToolButton, str]] = []

        self.setAcceptDrops(True)
        self.resize(1240, 860)
        self.setMinimumSize(760, 480)
        self.setWindowIcon(icons.app_icon())

        self.canvas = PdfCanvas()
        self.canvas.author = settings.value("author", os.environ.get("USERNAME", ""), type=str)
        self.canvas.invert = self.invert
        self.canvas.text_opts["size"] = float(settings.value("text_size", 12))
        tc = settings.value("text_color", "0,0,0", type=str)
        self.canvas.text_opts["color"] = tuple(int(v) for v in tc.split(","))

        self._build_ui()
        self._build_actions_and_toolbars()
        self._wire_canvas()
        self.apply_theme(self.dark, save=False)
        self.set_tool("select")
        self._update_enabled()
        geo = settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)

    # ================================================================== UI construction
    def _build_ui(self):
        central = QWidget()
        central.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)

        # welcome page
        w = QWidget()
        wl = QVBoxLayout(w)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_title = QLabel(APP_NAME)
        self.welcome_title.setStyleSheet("font-size:28pt;font-weight:600;")
        self.welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_hint = QLabel(T("welcome_hint"))
        self.welcome_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_hint.setStyleSheet("font-size:11pt;color:gray;")
        self.welcome_btn = QPushButton(T("open_pdf"))
        self.welcome_btn.setMinimumHeight(38)
        self.welcome_btn.setMinimumWidth(180)
        self.welcome_btn.clicked.connect(self.open_dialog)
        self.recent_label = QLabel(T("recent_files"))
        self.recent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.recent_list = QListWidget()
        self.recent_list.setMaximumWidth(560)
        self.recent_list.setMinimumWidth(420)
        self.recent_list.setMaximumHeight(260)
        self.recent_list.itemActivated.connect(lambda it: self.open_path(it.data(Qt.ItemDataRole.UserRole)))
        self.recent_list.itemClicked.connect(lambda it: self.open_path(it.data(Qt.ItemDataRole.UserRole)))
        wl.addStretch(1)
        wl.addWidget(self.welcome_title)
        wl.addWidget(self.welcome_hint)
        wl.addSpacing(10)
        wl.addWidget(self.welcome_btn, 0, Qt.AlignmentFlag.AlignCenter)
        wl.addSpacing(18)
        wl.addWidget(self.recent_label)
        wl.addWidget(self.recent_list, 0, Qt.AlignmentFlag.AlignCenter)
        wl.addStretch(2)
        self.stack.addWidget(w)

        # viewer page
        viewer = QWidget()
        vl = QHBoxLayout(viewer)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        vl.addWidget(self.splitter)

        self.sidebar = QTabWidget()
        self.sidebar.setMinimumWidth(170)
        self.sidebar.setMaximumWidth(420)
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbs.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumbs.setMovement(QListWidget.Movement.Static)
        self.thumbs.setIconSize(QSize(110, 150))
        self.thumbs.setSpacing(8)
        self.thumbs.setUniformItemSizes(False)
        self.thumbs.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.thumbs.currentRowChanged.connect(self._thumb_clicked)
        self.outline = QTreeWidget()
        self.outline.setHeaderHidden(True)
        self.outline.itemClicked.connect(self._outline_clicked)
        self.outline.setItemDelegate(AutoDirDelegate(self.outline))
        self.recent_list.setItemDelegate(AutoDirDelegate(self.recent_list))
        self.notes_list = QListWidget()
        self.notes_list.setItemDelegate(NoteDelegate(self.notes_list))
        self.notes_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.notes_list.itemClicked.connect(self._note_clicked)
        self.sidebar.addTab(self.thumbs, T("tab_pages"))
        self.sidebar.addTab(self.outline, T("tab_contents"))
        self.sidebar.addTab(self.notes_list, T("tab_notes"))
        self.sidebar.currentChanged.connect(self._sidebar_tab_changed)
        self.splitter.addWidget(self.sidebar)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.searchbar = SearchBar()
        self.searchbar.hide()
        rl.addWidget(self.searchbar)
        rl.addWidget(self.canvas, 1)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([210, 1000])
        self.sidebar.hide()
        self.stack.addWidget(viewer)

        self.thumb_timer = QTimer(self)
        self.thumb_timer.setInterval(12)
        self.thumb_timer.timeout.connect(self._thumb_tick)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(350)
        self.search_timer.timeout.connect(lambda: self.canvas.search(self.searchbar.edit.text(), restart=True))
        self.notes_timer = QTimer(self)
        self.notes_timer.setSingleShot(True)
        self.notes_timer.setInterval(400)
        self.notes_timer.timeout.connect(self._refresh_notes)

        self.searchbar.edit.textChanged.connect(lambda _: self.search_timer.start())
        self.searchbar.edit.returnPressed.connect(self._search_enter)
        self.searchbar.next.clicked.connect(lambda: self.canvas.search(self.searchbar.edit.text(), True))
        self.searchbar.prev.clicked.connect(lambda: self.canvas.search(self.searchbar.edit.text(), False))
        self.searchbar.close_btn.clicked.connect(self.close_search)

        self.setStatusBar(QStatusBar())
        self.hint_label = QLabel("")
        self.statusBar().addWidget(self.hint_label, 1)

    def _act(self, text, icon_name, slot=None, shortcut=None, checkable=False, tip=None) -> QAction:
        a = QAction(text, self)
        a.setCheckable(checkable)
        if slot:
            a.triggered.connect(slot)
        if shortcut:
            if isinstance(shortcut, (list, tuple)):
                a.setShortcuts([QKeySequence(s) for s in shortcut])
            else:
                a.setShortcut(QKeySequence(shortcut))
        full_tip = tip or text
        if shortcut:
            s0 = shortcut[0] if isinstance(shortcut, (list, tuple)) else shortcut
            full_tip += f"  ({s0})"
        a.setToolTip(full_tip)
        if icon_name:
            self._icon_actions.append((a, icon_name))
        return a

    def _build_actions_and_toolbars(self):
        # ---- file / view toolbar
        self.tb1 = QToolBar("main")
        self.tb1.setMovable(False)
        self.tb1.setIconSize(QSize(20, 20))
        self.tb1.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.tb1)

        self.act_open = self._act(T("open"), "open", self.open_dialog, "Ctrl+O")
        self.act_save = self._act(T("save"), "save", lambda: self.save(), "Ctrl+S")
        self.act_print = self._act(T("print"), "print", self.print_doc, "Ctrl+P")
        self.act_undo = self._act(T("undo"), "undo", lambda: self.canvas.undo(), "Ctrl+Z")
        self.act_redo = self._act(T("redo"), "redo", lambda: self.canvas.redo(), ["Ctrl+Y", "Ctrl+Shift+Z"])
        self.act_search = self._act(T("search"), "search", self.show_search, "Ctrl+F")
        self.act_sidebar = self._act(T("sidebar"), "sidebar", self.toggle_sidebar, "F4", checkable=True)
        self.act_prev = self._act(T("prev_page"), "up", lambda: self.canvas.goto_page(self.canvas.current_page - 1))
        self.act_next = self._act(T("next_page"), "down", lambda: self.canvas.goto_page(self.canvas.current_page + 1))
        self.act_zoom_out = self._act(T("zoom_out"), "zoom_out", lambda: self.canvas.zoom_by(1 / 1.2), "Ctrl+-")
        self.act_zoom_in = self._act(T("zoom_in"), "zoom_in", lambda: self.canvas.zoom_by(1.2), "Ctrl+=")
        self.act_fit_w = self._act(T("fit_width"), "fit_width", lambda: self.canvas.fit_width(), "Ctrl+2")
        self.act_fit_p = self._act(T("fit_page"), "fit_page", lambda: self.canvas.fit_page(), "Ctrl+0")
        self.act_rotate = self._act(T("rotate"), "rotate", lambda: self.canvas.rotate_all(90), "Ctrl+R")
        self.act_dark = self._act(T("dark_mode"), "moon", lambda: self.toggle_dark(), checkable=True)
        self.act_dark.setChecked(self.dark)
        for extra, key in ((QShortcut(QKeySequence("Ctrl++"), self), 1.2), ):
            extra.activated.connect(lambda: self.canvas.zoom_by(1.2))
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(lambda: self.canvas.set_zoom(1.0))
        QShortcut(QKeySequence("F3"), self).activated.connect(lambda: self.canvas.search(self.searchbar.edit.text(), True))
        QShortcut(QKeySequence("Shift+F3"), self).activated.connect(lambda: self.canvas.search(self.searchbar.edit.text(), False))
        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.new_window)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self).activated.connect(lambda: self.save_as())

        self.tb1.addAction(self.act_open)
        self.tb1.addAction(self.act_save)
        self.tb1.addAction(self.act_print)
        self.tb1.addSeparator()
        self.tb1.addAction(self.act_undo)
        self.tb1.addAction(self.act_redo)
        self.tb1.addSeparator()
        self.tb1.addAction(self.act_search)
        self.tb1.addAction(self.act_sidebar)
        self.tb1.addSeparator()
        self.tb1.addAction(self.act_prev)
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.setFixedWidth(62)
        self.page_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_spin.valueChanged.connect(self._spin_changed)
        self.page_total = QLabel(" / 0 ")
        self.tb1.addWidget(self.page_spin)
        self.tb1.addWidget(self.page_total)
        self.tb1.addAction(self.act_next)
        self.tb1.addSeparator()
        self.tb1.addAction(self.act_zoom_out)
        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.setFixedWidth(104)
        self.zoom_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.zoom_combo.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.zoom_combo.addItem(T("fit_width"), "width")
        self.zoom_combo.addItem(T("fit_page"), "page")
        for z in ZOOM_STEPS:
            self.zoom_combo.addItem(f"{z}%", z)
        self.zoom_combo.activated.connect(self._zoom_combo_activated)
        self.zoom_combo.lineEdit().editingFinished.connect(self._zoom_text_entered)
        self.tb1.addWidget(self.zoom_combo)
        self.tb1.addAction(self.act_zoom_in)
        self.tb1.addAction(self.act_fit_w)
        self.tb1.addAction(self.act_fit_p)
        self.tb1.addAction(self.act_rotate)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.tb1.addWidget(spacer)
        self.tb1.addAction(self.act_dark)
        self.menu_btn = QToolButton()
        self.menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_btn.setToolTip(T("more"))
        self.menu_btn.setMenu(self._build_main_menu())
        self._icon_actions.append((self.menu_btn, "menu"))
        self.tb1.addWidget(self.menu_btn)

        # ---- annotation toolbar
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        self.tb2 = QToolBar("tools")
        self.tb2.setMovable(False)
        self.tb2.setIconSize(QSize(20, 20))
        self.tb2.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.tb2)
        group = QActionGroup(self)
        group.setExclusive(True)

        def tool(name, text, icon_name, shortcut_hint):
            a = self._act(text, icon_name, lambda _=False, n=name: self._tool_clicked(n), checkable=True,
                          tip=f"{text}  ({shortcut_hint})" if shortcut_hint else text)
            group.addAction(a)
            self.tool_actions[name] = a
            return a

        self.tb2.addAction(tool("select", T("tool_select"), "select", "V"))
        self.tb2.addSeparator()
        # highlight with color dropdown
        self.btn_hl = self._tool_button(tool("highlight", T("tool_highlight"), "highlight", "H"), self._build_hl_menu())
        self.tb2.addWidget(self.btn_hl)
        self.tb2.addAction(tool("underline", T("tool_underline"), "underline", ""))
        self.tb2.addAction(tool("strike", T("tool_strike"), "strike", ""))
        self.tb2.addSeparator()
        self.tb2.addAction(tool("note", T("tool_note"), "note", "N"))
        self.btn_text = self._tool_button(tool("text", T("tool_text"), "text", "T"), self._build_text_menu())
        self.tb2.addWidget(self.btn_text)
        self.sign_menu = QMenu(self)
        self.sign_menu.aboutToShow.connect(self._fill_sign_menu)
        self.btn_sign = self._tool_button(tool("sign", T("tool_sign"), "sign", "S"), self.sign_menu)
        self.tb2.addWidget(self.btn_sign)
        self.tb2.addSeparator()
        self.act_delete = self._act(T("delete"), "trash", lambda: self.canvas.delete_selected(), tip=T("delete") + "  (Delete)")
        self.tb2.addAction(self.act_delete)

    def _tool_button(self, action: QAction, menu: QMenu) -> QToolButton:
        b = QToolButton()
        b.setDefaultAction(action)
        b.setMenu(menu)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        return b

    def _build_main_menu(self) -> QMenu:
        m = QMenu(self)
        m.addAction(T("new_window"), self.new_window)
        m.addAction(T("save_as"), lambda: self.save_as())
        m.addSeparator()
        self.act_invert = QAction(T("invert_pages"), self, checkable=True)
        self.act_invert.setChecked(self.invert)
        self.act_invert.toggled.connect(self.toggle_invert)
        m.addAction(self.act_invert)
        lang = m.addMenu(T("language"))
        for code, name in (("he", "עברית"), ("en", "English")):
            a = lang.addAction(name)
            a.setCheckable(True)
            a.setChecked(i18n.LANG == code)
            a.triggered.connect(lambda _=False, c=code: self.change_language(c))
        m.addAction(T("author_name"), self.set_author)
        m.addSeparator()
        m.addAction(T("help"), self.show_help)
        m.addAction(T("about"), self.show_about)
        return m

    def _build_hl_menu(self) -> QMenu:
        m = QMenu(self)
        for name, col in HL_COLORS:
            pm = QPixmap(16, 16)
            pm.fill(QColor.fromRgbF(*col))
            a = m.addAction(QIcon(pm), T("hl_" + name))
            a.triggered.connect(lambda _=False, c=col: self._pick_hl_color(c))
        return m

    def _build_text_menu(self) -> QMenu:
        m = QMenu(self)
        m.addAction(T("text_free"), lambda: self._pick_text_preset(None))
        m.addAction("✓  " + T("text_check"), lambda: self._pick_text_preset("check"))
        m.addAction("✗  " + T("text_cross"), lambda: self._pick_text_preset("cross"))
        m.addAction(T("text_date") + "  " + QDate.currentDate().toString("dd/MM/yyyy"),
                    lambda: self._pick_text_preset("date"))
        m.addSeparator()
        sm = m.addMenu(T("text_size"))
        for s in TEXT_SIZES:
            sm.addAction(str(s), lambda _=False, v=s: self._set_text_size(v))
        cm = m.addMenu(T("text_color"))
        for key, col in TEXT_COLORS:
            pm = QPixmap(16, 16)
            pm.fill(QColor(*col))
            cm.addAction(QIcon(pm), T(key), lambda _=False, c=col: self._set_text_color(c))
        return m

    # ================================================================== canvas wiring
    def _wire_canvas(self):
        c = self.canvas
        c.pageChanged.connect(self._page_changed)
        c.zoomChanged.connect(self._zoom_changed)
        c.dirtyChanged.connect(lambda _: self._update_title())
        c.undoStateChanged.connect(self._update_enabled)
        c.selectionChanged.connect(lambda _: self._update_enabled())
        c.requestToolReset.connect(lambda: self.set_tool("select"))
        c.statusMessage.connect(lambda s: self.statusBar().showMessage(s, 2500))
        c.annotsChanged.connect(self._annots_changed)
        c.searchResult.connect(self._search_result)
        c.toolShortcut.connect(self._tool_clicked)

    # ================================================================== theme / icons
    def apply_theme(self, dark: bool, save=True):
        self.dark = dark
        app = QApplication.instance()
        app.setStyle("Fusion")
        hints = app.styleHints()
        if hasattr(hints, "setColorScheme"):       # Qt >= 6.8: also darkens the title bar
            hints.setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
        pal = QPalette()
        if dark:
            def c(h):
                return QColor(h)
            pal.setColor(QPalette.ColorRole.Window, c("#2b2d30"))
            pal.setColor(QPalette.ColorRole.WindowText, c("#e3e5e8"))
            pal.setColor(QPalette.ColorRole.Base, c("#1f2023"))
            pal.setColor(QPalette.ColorRole.AlternateBase, c("#2b2d30"))
            pal.setColor(QPalette.ColorRole.Text, c("#e3e5e8"))
            pal.setColor(QPalette.ColorRole.Button, c("#383b3f"))
            pal.setColor(QPalette.ColorRole.ButtonText, c("#e3e5e8"))
            pal.setColor(QPalette.ColorRole.ToolTipBase, c("#383b3f"))
            pal.setColor(QPalette.ColorRole.ToolTipText, c("#e3e5e8"))
            pal.setColor(QPalette.ColorRole.Highlight, c("#3d7eff"))
            pal.setColor(QPalette.ColorRole.HighlightedText, c("#ffffff"))
            pal.setColor(QPalette.ColorRole.PlaceholderText, c("#8b9096"))
            pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, c("#76797d"))
            pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, c("#76797d"))
            pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, c("#76797d"))
        else:
            def c(h):
                return QColor(h)
            pal.setColor(QPalette.ColorRole.Window, c("#f1f2f4"))
            pal.setColor(QPalette.ColorRole.WindowText, c("#202327"))
            pal.setColor(QPalette.ColorRole.Base, c("#ffffff"))
            pal.setColor(QPalette.ColorRole.AlternateBase, c("#f1f2f4"))
            pal.setColor(QPalette.ColorRole.Text, c("#202327"))
            pal.setColor(QPalette.ColorRole.Button, c("#e6e8eb"))
            pal.setColor(QPalette.ColorRole.ButtonText, c("#202327"))
            pal.setColor(QPalette.ColorRole.ToolTipBase, c("#ffffe1"))
            pal.setColor(QPalette.ColorRole.ToolTipText, c("#202327"))
            pal.setColor(QPalette.ColorRole.Highlight, c("#3d7eff"))
            pal.setColor(QPalette.ColorRole.HighlightedText, c("#ffffff"))
            pal.setColor(QPalette.ColorRole.PlaceholderText, c("#7a7f85"))
            pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, c("#a3a7ac"))
            pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, c("#a3a7ac"))
            pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, c("#a3a7ac"))
        app.setPalette(pal)
        app.setStyleSheet(
            "QToolBar{spacing:3px;padding:3px;border:none;}"
            "QToolButton{padding:4px 6px;border-radius:5px;border:1px solid transparent;}"
            "QToolButton:hover{background:rgba(128,128,128,45);}"
            "QToolButton:checked{background:rgba(61,126,255,70);border:1px solid rgba(61,126,255,170);}"
            "QToolButton:pressed{background:rgba(61,126,255,110);}"
            "QToolButton::menu-button{border:none;width:14px;}"
            "QToolTip{padding:3px;}"
        )
        self.canvas.dark_bg = dark
        self.canvas.viewport().update()
        self._refresh_icons()
        if hasattr(self, "act_dark"):
            self.act_dark.blockSignals(True)
            self.act_dark.setChecked(dark)
            self.act_dark.blockSignals(False)
        if save:
            self.settings.setValue("dark", dark)

    def _refresh_icons(self):
        col = "#e3e5e8" if self.dark else "#34373b"
        for obj, name in self._icon_actions:
            obj.setIcon(icons.icon(name, col))
        self.searchbar.set_icons(col)

    def toggle_dark(self):
        self.apply_theme(not self.dark)

    def toggle_invert(self, on: bool):
        self.invert = on
        self.canvas.set_invert(on)
        self.settings.setValue("invert", on)

    # ================================================================== tools
    def _tool_clicked(self, name: str):
        c = self.canvas
        if name in MARKUP_TOOLS and c.has_selection():
            c.apply_markup(name)
            self.set_tool("select")
            return
        if name == "sign":
            if c.tool == "sign":
                self.set_tool("select")
            else:
                self._start_sign()
            return
        if name == c.tool and name != "select":
            name = "select"
        if name == "text":
            pass
        self.set_tool(name)

    def set_tool(self, name: str):
        self.tool_actions[name].setChecked(True)
        self.canvas.set_tool(name)
        hints = {
            "select": T("hint_select"), "highlight": T("hint_highlight"),
            "underline": T("hint_highlight"), "strike": T("hint_highlight"),
            "note": T("hint_note"), "text": T("hint_text"), "sign": T("hint_sign"),
        }
        self.hint_label.setText(hints.get(name, ""))

    def _pick_hl_color(self, col):
        self.canvas.hl_color = col
        if self.canvas.has_selection():
            self.canvas.apply_markup("highlight")
            self.set_tool("select")
        else:
            self.set_tool("highlight")

    def _pick_text_preset(self, preset):
        self.canvas.text_preset = preset
        self.set_tool("text")
        self.hint_label.setText(T("hint_text") if preset is None else T("hint_preset"))

    def _set_text_size(self, v):
        self.canvas.text_opts["size"] = float(v)
        self.settings.setValue("text_size", v)
        self._pick_text_preset(self.canvas.text_preset)

    def _set_text_color(self, col):
        self.canvas.text_opts["color"] = tuple(col)
        self.settings.setValue("text_color", ",".join(str(v) for v in col))
        self._pick_text_preset(self.canvas.text_preset)

    # ---- signatures
    def _sig_icon(self, path: Path) -> QIcon:
        img = QImage(str(path))
        pm = QPixmap(150, 46)
        pm.fill(QColor("white"))
        if not img.isNull():
            sc = img.scaled(140, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            p = QPainter(pm)
            p.drawImage((150 - sc.width()) // 2, (46 - sc.height()) // 2, sc)
            p.end()
        return QIcon(pm)

    def _fill_sign_menu(self):
        m = self.sign_menu
        m.clear()
        m.setIconSize(QSize(150, 46))
        sigs = self.store.list()
        for p in sigs:
            a = m.addAction(self._sig_icon(p), "")
            a.triggered.connect(lambda _=False, pp=p: self._use_signature(pp))
        if sigs:
            m.addSeparator()
        m.addAction(icons.icon("plus", "#e3e5e8" if self.dark else "#34373b"), T("new_signature"),
                    self._new_signature)
        if sigs:
            dm = m.addMenu(icons.icon("trash", "#e3e5e8" if self.dark else "#34373b"), T("delete_signature"))
            dm.setIconSize(QSize(150, 46))
            for p in sigs:
                a = dm.addAction(self._sig_icon(p), "")
                a.triggered.connect(lambda _=False, pp=p: self._delete_signature(pp))

    def _start_sign(self):
        sigs = self.store.list()
        if not sigs:
            self._new_signature()
            return
        p = self.last_sig if self.last_sig and self.last_sig.exists() else sigs[0]
        self._use_signature(p)

    def _new_signature(self):
        dlg = SignatureDialog(self, name_hint=self.canvas.author if self.canvas.author != os.environ.get("USERNAME") else "")
        if dlg.exec() == SignatureDialog.DialogCode.Accepted and dlg.png:
            p = self.store.add_png(dlg.png)
            self._use_signature(p)
        else:
            self.set_tool("select")

    def _use_signature(self, path: Path):
        try:
            png = path.read_bytes()
        except OSError:
            return
        img = QImage.fromData(png)
        if img.isNull():
            return
        self.last_sig = path
        c = self.canvas
        c.pending_png = png
        c.pending_img = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        aspect = img.height() / max(1, img.width())
        c.pending_w_pt = 150.0 if aspect < 0.45 else max(70.0, 150.0 * 0.45 / aspect)
        self.set_tool("sign")

    def _delete_signature(self, path: Path):
        if QMessageBox.question(self, T("delete_signature"), T("delete_signature_q")) == QMessageBox.StandardButton.Yes:
            self.store.delete(path)
            if self.last_sig == path:
                self.last_sig = None

    # ================================================================== enable / title / status
    def _update_enabled(self):
        has = self.canvas.doc is not None
        for a in (self.act_save, self.act_print, self.act_search, self.act_prev, self.act_next,
                  self.act_zoom_in, self.act_zoom_out, self.act_fit_p, self.act_fit_w, self.act_rotate,
                  self.act_sidebar):
            a.setEnabled(has)
        for a in self.tool_actions.values():
            a.setEnabled(has)
        for b in (self.btn_hl, self.btn_text, self.btn_sign):
            b.setEnabled(has)
        self.page_spin.setEnabled(has)
        self.zoom_combo.setEnabled(has)
        self.act_undo.setEnabled(has and self.canvas.can_undo())
        self.act_redo.setEnabled(has and self.canvas.can_redo())
        self.act_delete.setEnabled(has and self.canvas.sel_annot is not None)

    def _update_title(self):
        c = self.canvas
        if not c.doc:
            self.setWindowTitle(APP_NAME)
            return
        name = os.path.basename(c.path) if c.path else T("untitled")
        self.setWindowTitle(f"{'● ' if c.is_dirty else ''}{name} — {APP_NAME}")
        self.act_save.setEnabled(True)

    def _page_changed(self, n: int):
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(n + 1)
        self.page_spin.blockSignals(False)
        if 0 <= n < self.thumbs.count() and self.sidebar.isVisible():
            self.thumbs.blockSignals(True)
            self.thumbs.setCurrentRow(n)
            self.thumbs.blockSignals(False)
            self.thumbs.scrollToItem(self.thumbs.item(n))

    def _spin_changed(self, v: int):
        self.canvas.goto_page(v - 1)

    def _zoom_changed(self, z: float):
        self._zoom_guard = True
        c = self.canvas
        if c.fit_mode == "width":
            self.zoom_combo.setCurrentIndex(0)
        elif c.fit_mode == "page":
            self.zoom_combo.setCurrentIndex(1)
        else:
            self.zoom_combo.setCurrentIndex(-1)
            self.zoom_combo.setEditText(f"{round(z * 100)}%")
        self._zoom_guard = False

    def _zoom_combo_activated(self, idx: int):
        if self._zoom_guard:
            return
        d = self.zoom_combo.itemData(idx)
        if d == "width":
            self.canvas.fit_width()
        elif d == "page":
            self.canvas.fit_page()
        elif d:
            self.canvas.set_zoom(d / 100.0)
        self.canvas.setFocus()

    def _zoom_text_entered(self):
        if self._zoom_guard:
            return
        t = self.zoom_combo.lineEdit().text().replace("%", "").strip()
        try:
            v = float(t)
            self.canvas.set_zoom(max(10.0, min(800.0, v)) / 100.0)
        except ValueError:
            pass

    # ================================================================== search
    def show_search(self):
        if not self.canvas.doc:
            return
        self.searchbar.show()
        self.searchbar.edit.setFocus()
        self.searchbar.edit.selectAll()

    def close_search(self):
        self.searchbar.hide()
        self.searchbar.count.setText("")
        self.canvas.clear_search()
        self.canvas.setFocus()

    def _search_enter(self):
        mods = QApplication.keyboardModifiers()
        self.search_timer.stop()
        self.canvas.search(self.searchbar.edit.text(), not (mods & Qt.KeyboardModifier.ShiftModifier))

    def _search_result(self, cur: int, total: int):
        if not self.searchbar.edit.text():
            self.searchbar.count.setText("")
        elif total == 0:
            self.searchbar.count.setText(T("no_results"))
        else:
            self.searchbar.count.setText(f"{cur} / {total}")

    # ================================================================== sidebar
    def toggle_sidebar(self):
        vis = not self.sidebar.isVisible()
        self.sidebar.setVisible(vis)
        self.act_sidebar.setChecked(vis)
        if vis:
            self.splitter.setSizes([210, max(400, self.width() - 210)])
            self.thumb_timer.start()
            self._page_changed(self.canvas.current_page)
            self._sidebar_tab_changed(self.sidebar.currentIndex())
        else:
            self.thumb_timer.stop()

    def _build_sidebar(self):
        doc = self.canvas.doc
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        self._thumb_done.clear()
        n = doc.page_count
        blank = {}
        for i in range(n):
            r = self.canvas.page_rects[i]
            w = 110
            h = max(20, int(w * r.height / max(r.width, 1)))
            key = (w, h)
            if key not in blank:
                pm = QPixmap(w, h)
                pm.fill(QColor("white"))
                blank[key] = QIcon(pm)
            it = QListWidgetItem(blank[key], str(i + 1))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            it.setSizeHint(QSize(w + 14, h + 28))
            self.thumbs.addItem(it)
        self.thumbs.blockSignals(False)
        # outline
        self.outline.clear()
        try:
            toc = doc.get_toc()
        except Exception:
            toc = []
        stack: list[tuple[int, QTreeWidgetItem]] = []
        for lvl, title, page, *_ in toc:
            it = QTreeWidgetItem([title])
            it.setData(0, Qt.ItemDataRole.UserRole, page - 1)
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            if stack:
                stack[-1][1].addChild(it)
            else:
                self.outline.addTopLevelItem(it)
            stack.append((lvl, it))
        self.outline.expandAll()
        self.sidebar.setTabEnabled(1, bool(toc))
        self._notes_stale = True

    def _thumb_tick(self):
        if not self.canvas.doc or not self.sidebar.isVisible() or self.sidebar.currentIndex() != 0:
            return
        cur = self.canvas.current_page
        n = self.thumbs.count()
        todo = [i for i in range(max(0, cur - 20), min(n, cur + 120)) if i not in self._thumb_done]
        if not todo:
            return
        todo.sort(key=lambda i: abs(i - cur))
        for i in todo[:3]:
            self._thumb_done.add(i)
            try:
                page = self.canvas.doc[i]
                z = 150.0 / max(page.rect.width, 1)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
                img = QImage(bytes(pix.samples), pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
                if self.invert:
                    img.invertPixels()
                pm = QPixmap.fromImage(img.scaledToWidth(110, Qt.TransformationMode.SmoothTransformation))
                it = self.thumbs.item(i)
                it.setIcon(QIcon(pm))
                it.setSizeHint(QSize(124, pm.height() + 28))
            except Exception:
                pass

    def _thumb_clicked(self, row: int):
        if row >= 0:
            self.canvas.goto_page(row)

    def _outline_clicked(self, item, _col=0):
        p = item.data(0, Qt.ItemDataRole.UserRole)
        if p is not None and p >= 0:
            self.canvas.goto_page(p)

    def _sidebar_tab_changed(self, idx: int):
        if idx == 2 and self._notes_stale:
            self._refresh_notes()

    def _annots_changed(self):
        self._notes_stale = True
        self._thumb_done.discard(self.canvas.current_page)
        if self.sidebar.isVisible() and self.sidebar.currentIndex() == 2:
            self.notes_timer.start()
        self._update_enabled()

    def _refresh_notes(self):
        self.notes_list.clear()
        self._notes_stale = False
        for pg, xref, kind, text in self.canvas.collect_notes():
            it = QListWidgetItem(text)
            it.setData(HEAD_ROLE, f"{T('page')} {pg + 1}" + ("  ·  " + T("tool_note") if kind == A_TEXT else ""))
            it.setData(Qt.ItemDataRole.UserRole, (pg, xref))
            self.notes_list.addItem(it)
        if self.notes_list.count() == 0:
            it = QListWidgetItem(T("no_notes"))
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.notes_list.addItem(it)

    def _note_clicked(self, item):
        d = item.data(Qt.ItemDataRole.UserRole)
        if d:
            self.canvas.select_annot(*d)

    # ================================================================== open / close
    def open_dialog(self):
        start = self.settings.value("last_dir", str(Path.home() / "Documents"), type=str)
        path, _ = QFileDialog.getOpenFileName(self, T("open_pdf"), start, "PDF (*.pdf);;*.*")
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        path = os.path.abspath(path)
        if self.canvas.doc and not self._maybe_save():
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, APP_NAME, T("file_missing", path))
            self._forget_recent(path)
            return
        try:
            doc = pymupdf.open(path)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, T("open_failed", str(e)))
            return
        pw = None
        if doc.needs_pass:
            for _ in range(3):
                pw, ok = QInputDialog.getText(self, T("password"), T("password_prompt"), QLineEdit.EchoMode.Password)
                if not ok:
                    doc.close()
                    return
                if doc.authenticate(pw):
                    break
            else:
                doc.close()
                QMessageBox.warning(self, APP_NAME, T("wrong_password"))
                return
        if doc.page_count == 0:
            doc.close()
            QMessageBox.warning(self, APP_NAME, T("empty_pdf"))
            return
        self._save_position()
        self._password = pw
        self._load(doc, path)

    def _load(self, doc: pymupdf.Document, path: str, restore_state: dict | None = None):
        c = self.canvas
        old = c.doc
        c.set_document(doc, path)
        if old is not None and old is not doc:
            try:
                old.close()
            except Exception:
                pass
        self._overwrite_ok = False
        self.stack.setCurrentIndex(1)
        n = doc.page_count
        self.page_spin.blockSignals(True)
        self.page_spin.setRange(1, n)
        self.page_spin.setValue(1)
        self.page_spin.blockSignals(False)
        self.page_total.setText(f" / {n} ")
        self._build_sidebar()
        self.settings.setValue("last_dir", os.path.dirname(path))
        self._add_recent(path)
        state = restore_state or self._saved_position(path)
        if state:
            mode = state.get("fit")
            if mode:
                c.set_zoom(c.zoom, mode)
            else:
                c.set_zoom(float(state.get("zoom", 1.0)))
            c.goto_page(int(state.get("page", 0)), float(state.get("y", 0)))
        else:
            c.set_zoom(c.zoom, "width")
        if self.sidebar.isVisible():
            self.thumb_timer.start()
        self._update_title()
        self._update_enabled()
        self._zoom_changed(c.zoom)
        self._page_changed(c.current_page)
        self.set_tool("select")
        c.setFocus()

    def close_document(self):
        self.canvas.set_document(None, None)
        self.stack.setCurrentIndex(0)
        self._refresh_recent_list()
        self._update_title()
        self._update_enabled()

    # ---- recents / positions
    def _recents(self) -> list[str]:
        v = self.settings.value("recent", [])
        if isinstance(v, str):
            v = [v]
        return [p for p in (v or [])]

    def _add_recent(self, path: str):
        r = [p for p in self._recents() if os.path.normcase(p) != os.path.normcase(path)]
        r.insert(0, path)
        self.settings.setValue("recent", r[:12])

    def _forget_recent(self, path: str):
        self.settings.setValue("recent", [p for p in self._recents() if p != path])
        self._refresh_recent_list()

    def _refresh_recent_list(self):
        self.recent_list.clear()
        rec = [p for p in self._recents() if os.path.exists(p)]
        self.recent_label.setVisible(bool(rec))
        self.recent_list.setVisible(bool(rec))
        for p in rec:
            it = QListWidgetItem(f"{os.path.basename(p)}\n{os.path.dirname(p)}")
            it.setData(Qt.ItemDataRole.UserRole, p)
            self.recent_list.addItem(it)

    def _positions(self) -> dict:
        try:
            return json.loads(self.settings.value("positions", "{}", type=str))
        except Exception:
            return {}

    def _saved_position(self, path: str) -> dict | None:
        return self._positions().get(os.path.normcase(path))

    def _view_state(self) -> dict:
        c = self.canvas
        y = 0.0
        if c.tops:
            y = max(0.0, (c.verticalScrollBar().value() - c.tops[c.current_page] + 8) / c.s)
        return {"page": c.current_page, "zoom": round(c.zoom, 3), "fit": c.fit_mode, "y": round(y, 1)}

    def _save_position(self):
        c = self.canvas
        if not c.doc or not c.path:
            return
        pos = self._positions()
        key = os.path.normcase(c.path)
        pos.pop(key, None)
        pos[key] = self._view_state()
        while len(pos) > 200:
            pos.pop(next(iter(pos)))
        self.settings.setValue("positions", json.dumps(pos))

    # ================================================================== save / print
    def _maybe_save(self) -> bool:
        """Return True when it is OK to discard / replace the current document."""
        c = self.canvas
        if not c.doc or not c.is_dirty:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(APP_NAME)
        box.setText(T("unsaved_q", os.path.basename(c.path or T("untitled"))))
        b_save = box.addButton(T("save"), QMessageBox.ButtonRole.AcceptRole)
        b_copy = box.addButton(T("save_as"), QMessageBox.ButtonRole.ActionRole)
        b_disc = box.addButton(T("discard"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(T("cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is b_save:
            return self.save()
        if clicked is b_copy:
            return self.save_as()
        return clicked is b_disc

    def save(self) -> bool:
        c = self.canvas
        if not c.doc:
            return False
        if not c.path:
            return self.save_as()
        if not c.is_dirty:
            self.statusBar().showMessage(T("nothing_to_save"), 2000)
            return True
        if not self._overwrite_ok:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(T("save"))
            box.setText(T("overwrite_q", os.path.basename(c.path)))
            b_over = box.addButton(T("overwrite"), QMessageBox.ButtonRole.AcceptRole)
            b_copy = box.addButton(T("save_copy"), QMessageBox.ButtonRole.ActionRole)
            box.addButton(T("cancel"), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is b_copy:
                return self.save_as()
            if clicked is not b_over:
                return False
            self._overwrite_ok = True
        return self._write(c.path)

    def save_as(self) -> bool:
        c = self.canvas
        if not c.doc:
            return False
        base = Path(c.path) if c.path else Path.home() / "Documents" / "document.pdf"
        suggestion = str(base.with_name(base.stem + T("copy_suffix") + ".pdf"))
        path, _ = QFileDialog.getSaveFileName(self, T("save_as"), suggestion, "PDF (*.pdf)")
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        if c.path and os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(c.path)):
            self._overwrite_ok = True
            return self._write(c.path)
        return self._write(path)

    def _write(self, target: str) -> bool:
        """Write the document to target (in place if it is the open file)."""
        c = self.canvas
        doc = c.doc
        state = self._view_state()
        try:
            c.purge_trashed()
            in_place = c.path and os.path.normcase(os.path.abspath(target)) == os.path.normcase(os.path.abspath(c.path))
            if in_place and doc.can_save_incrementally():
                doc.saveIncr()
            else:
                tmp = target + ".litepdf.tmp"
                doc.save(tmp, garbage=1, deflate=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
                doc.close()
                os.replace(tmp, target)
            if not doc.is_closed:
                doc.close()
            # Always reopen from disk: PyMuPDF's in-memory state can go stale after a save
            # (e.g. a later rotate + incremental save would drop annotations).
            new = pymupdf.open(target)
            if new.needs_pass and self._password:
                new.authenticate(self._password)
            self._load(new, target, restore_state=state)
            self._update_title()
            self.statusBar().showMessage(T("saved_to", os.path.basename(target)), 3500)
            return True
        except Exception as e:
            QMessageBox.critical(self, T("save"), T("save_failed", str(e)))
            if c.doc is not None and c.doc.is_closed:
                try:
                    self._load(pymupdf.open(c.path), c.path, restore_state=state)
                except Exception:
                    pass
            return False

    def print_doc(self):
        if not self.canvas.doc:
            return
        printing.print_document(self, self.canvas.doc, self.canvas.current_page)

    # ================================================================== misc menu actions
    def new_window(self):
        args = [] if getattr(sys, "frozen", False) else [script_path()]
        QProcess.startDetached(sys.executable, args)

    def change_language(self, code: str):
        if code == i18n.LANG:
            return
        if not self._maybe_save():
            return
        self.settings.setValue("lang", code)
        self._save_position()
        args = [] if getattr(sys, "frozen", False) else [script_path()]
        if self.canvas.path:
            args.append(self.canvas.path)
        QProcess.startDetached(sys.executable, args)
        self._force_close = True
        self.close()

    def set_author(self):
        t, ok = QInputDialog.getText(self, T("author_name"), T("author_prompt"), text=self.canvas.author)
        if ok:
            self.canvas.author = t.strip()
            self.settings.setValue("author", self.canvas.author)

    def show_help(self):
        QMessageBox.information(self, T("help"), T("help_text"))

    def show_about(self):
        QMessageBox.about(self, T("about"), T("about_text", APP_NAME))

    # ================================================================== events
    def closeEvent(self, ev):
        if not self._force_close and not self._maybe_save():
            ev.ignore()
            return
        self._save_position()
        self.settings.setValue("geometry", self.saveGeometry())
        self.canvas.set_document(None, None)
        ev.accept()

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith(".pdf") for u in ev.mimeData().urls()):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        files = [u.toLocalFile() for u in ev.mimeData().urls() if u.toLocalFile().lower().endswith(".pdf")]
        if not files:
            return
        self.open_path(files[0])
        for extra in files[1:]:
            args = [] if getattr(sys, "frozen", False) else [script_path()]
            QProcess.startDetached(sys.executable, args + [extra])

    def showEvent(self, ev):
        super().showEvent(ev)
        if self.canvas.doc is None:
            self._refresh_recent_list()
