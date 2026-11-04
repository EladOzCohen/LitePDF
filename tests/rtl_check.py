import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import Qt
app = QApplication([])
from popups import NotePopup, TextPopup
from textrender import render_text

out = sys.argv[1]
pop = NotePopup(None, "שלום עולם, זו הערה בעברית.\nThis line is English text.\nשורה נוספת עם English באמצע 123 וסוף.")
pop.resize(340, 190)
pop.show()
pop.grab().save(os.path.join(out, "note.png"))

img, w, h = render_text("שלום עולם, זה טקסט\nHello world mixed שלום 12/11/2026", 14)
bg = QImage(img.width() + 20, img.height() + 20, QImage.Format.Format_ARGB32_Premultiplied)
bg.fill(Qt.GlobalColor.white)
p = QPainter(bg); p.drawImage(10, 10, img); p.end()
bg.save(os.path.join(out, "render.png"))
print("sizes", w, h)
