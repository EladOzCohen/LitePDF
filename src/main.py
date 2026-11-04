"""LitePDF entry point."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


def _install_crash_handler():
    """Under pythonw there is no console: write unexpected errors to a log and tell the user."""
    import traceback
    import time

    def hook(etype, value, tb):
        text = "".join(traceback.format_exception(etype, value, tb))
        try:
            d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LitePDF")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "crash.log"), "a", encoding="utf-8") as f:
                f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n{text}")
        except OSError:
            pass
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "LitePDF", "Unexpected error (details in %APPDATA%\\LitePDF\\crash.log):\n\n"
                                 + str(value))
        except Exception:
            pass
        sys.__excepthook__(etype, value, tb)

    sys.excepthook = hook


def main():
    app = QApplication(sys.argv)
    _install_crash_handler()
    app.setOrganizationName("LitePDF")
    app.setApplicationName("LitePDF")
    settings = QSettings("LitePDF", "LitePDF")

    import i18n
    i18n.set_lang(settings.value("lang", "he", type=str))
    import strings  # noqa: F401  (fills i18n.S)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if i18n.LANG == "he" else Qt.LayoutDirection.LeftToRight)
    f = QFont("Segoe UI")
    f.setPointSizeF(9.5)
    app.setFont(f)

    from main_window import MainWindow
    win = MainWindow(settings)
    win.show()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args and os.path.isfile(args[0]):
        win.open_path(args[0])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
