"""Post REAL Win32 mouse messages (WM_LBUTTONDOWN/MOUSEMOVE/UP) to the main window and see what the app does."""
import ctypes, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
import pymupdf
from PySide6.QtCore import QSettings, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
app = QApplication([])
import i18n, strings  # noqa
from main_window import MainWindow
path = sys.argv[1]
tool = sys.argv[2] if len(sys.argv) > 2 else "highlight"
win = MainWindow(QSettings(os.path.join(os.environ["TEMP"], "w32.ini"), QSettings.Format.IniFormat))
win.show(); win.open_path(path); QTest.qWait(400)
c = win.canvas; vp = c.viewport()
win.set_tool(tool)
from PySide6.QtCore import QObject, QEvent
class Spy(QObject):
    log = []
    def eventFilter(self, o, e):
        if e.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseMove, QEvent.Type.MouseButtonDblClick):
            Spy.log.append((e.type().name, int(e.position().x()), int(e.buttons().value), c.sel_words, (c._drag or {}).get('kind'), c._moved))
        return False
spy = Spy(); vp.installEventFilter(spy)
user32 = ctypes.windll.user32
hwnd = int(win.winId())
dpr = win.devicePixelRatioF()
print("dpr", dpr, "tool", c.tool)
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x200, 0x201, 0x202
def post(msg, wparam, pt):
    g = vp.mapTo(win, pt)
    x, y = int(g.x() * dpr), int(g.y() * dpr)
    user32.PostMessageW(hwnd, msg, wparam, (y << 16) | (x & 0xFFFF))
    QTest.qWait(12)
# pick a line with many words on the visible page
pg = c.current_page
words = c._get_words(pg)
rows = {}
for w in words: rows.setdefault((w[5], w[6]), []).append(w)
def vis(v):
    y = c._to_px(pg, 0, v[0][1]).y()
    return 60 < y < vp.height() - 60
line = max((v for v in rows.values() if 6 <= len(v) <= 14 and vis(v)), key=len)
a, b = line[0], line[-1]
def px(x, y):
    p = c._to_px(pg, x, y); return QPoint(int(p.x()), int(p.y()))
pa, pb = px((a[0]+a[2])/2, (a[1]+a[3])/2), px((b[0]+b[2])/2, (b[1]+b[3])/2)
print("line words:", len(line), "press", pa, "release", pb)
post(WM_MOUSEMOVE, 0, pa)
post(WM_LBUTTONDOWN, 1, pa)
for s in range(1, 31):                      # 30 intermediate moves, like a real hand
    post(WM_MOUSEMOVE, 1, QPoint(pa.x() + (pb.x()-pa.x())*s//30, pa.y() + (pb.y()-pa.y())*s//30))
    if s == 3: print("  during drag: sel =", c.sel_words, "drag kind =", (c._drag or {}).get("kind"))
post(WM_LBUTTONUP, 0, pb)
QTest.qWait(100)
hl = [x for x in c._get_annots(pg) if x.kind == 8]
print("RESULT: sel_words =", c.sel_words, "| highlights:", len(hl), "| quads:", [len(h.quads) for h in hl],
      "| covered width pt:", [round(h.rect.width) for h in hl], "| line width pt:", round(b[2]-a[0]))

print("events seen by viewport:", len(Spy.log))
for r in Spy.log[:6] + [('...',)] + Spy.log[-6:]: print("  ", r)
