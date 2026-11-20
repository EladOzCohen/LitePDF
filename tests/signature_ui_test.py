"""Signature dialog (draw + type), saved library and the Sign dropdown must work (they crashed / were empty before)."""
import os, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
OUT = sys.argv[1]
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="sigtest_")         # keep the user's real signature library untouched
from PySide6.QtCore import Qt, QPoint, QSettings, QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
app = QApplication([])
import i18n, strings  # noqa
from main_window import MainWindow
from signature import SignatureDialog
import subprocess
failed = False
def check(c, m):
    global failed
    print(("PASS " if c else "FAIL ") + m); failed = failed or not c
sample = os.path.join(OUT, "sample.pdf")
if not os.path.exists(sample):
    subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, "make_sample.py"), sample], check=True)
win = MainWindow(QSettings(os.path.join(OUT, "sig.ini"), QSettings.Format.IniFormat)); win.show(); win.open_path(sample); QTest.qWait(200)
dlg = SignatureDialog(win); dlg.show(); QApplication.processEvents()
dlg.grab().save(os.path.join(OUT, "sigdlg_draw.png"))
check(True, "dialog opens and paints (no crash)")
pad = dlg.pad
check(not dlg.ok.isEnabled(), "Save disabled while nothing drawn")
QTest.mousePress(pad, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(60, 120))
for k in range(1, 30):
    QTest.mouseMove(pad, QPoint(60 + k * 12, 120 + int(40 * (1 if k % 2 else -1) * (k % 5) / 5))); QApplication.processEvents()
QTest.mouseRelease(pad, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(420, 120))
check(dlg.ok.isEnabled(), "Save enabled after drawing")
img = pad.image(); check(img is not None and img.width() > 100, f"drawn image exported ({img.width()}x{img.height()})")
pad.set_width(5.0); check(abs(pad.pen_w - 5.0) < 1e-6, "thickness changes")
dlg.grab().save(os.path.join(OUT, "sigdlg_drawn.png"))
dlg._accept(); check(dlg.png and dlg.png[:4] == b"\x89PNG", "dialog returns PNG bytes")
# type tab, Hebrew name -> only fonts with Hebrew glyphs are offered
d2 = SignatureDialog(win); d2.show(); d2.tabs.setCurrentIndex(1)
d2.typepad.edit.setText("אלעד כהן"); QApplication.processEvents()
visible = [d2.typepad.fonts.item(i).data(Qt.ItemDataRole.UserRole) for i in range(d2.typepad.fonts.count()) if not d2.typepad.fonts.item(i).isHidden()]
print("fonts offered for a Hebrew name:", visible)
check(len(visible) >= 1 and "Segoe Script" not in visible, "Hebrew name only offers fonts with Hebrew glyphs")
check(d2.ok.isEnabled(), "typed signature can be saved")
d2.grab().save(os.path.join(OUT, "sigdlg_type_he.png")); d2.close()
# library + dropdown
p1 = win.store.add_png(dlg.png); import time; time.sleep(1.1); p2 = win.store.add_png(dlg.png)
win._fill_sign_menu()
acts = win.sign_menu.actions()
print("menu entries:", len(acts))
check(len(acts) >= 5, "Sign dropdown lists the saved signatures + 'new' + 'delete' submenu")
win.sign_menu.popup(win.mapToGlobal(QPoint(300, 120))); QApplication.processEvents()
win.sign_menu.grab().save(os.path.join(OUT, "sign_menu.png")); win.sign_menu.hide()
win._use_signature(p1); check(win.canvas.tool == "sign", "choosing a signature arms the Sign tool")
win._delete_signature.__func__  # exists
check(win._start_sign is not None, "start_sign available")
print("FAILED" if failed else "ALL OK")
