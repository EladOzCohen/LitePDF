"""Write the app icon (drawn in code) to an .ico file: make_icon.py out.ico"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from PySide6.QtGui import QGuiApplication, QImage

app = QGuiApplication([])
import icons

ic = icons.app_icon()
pm = ic.pixmap(256, 256)
ok = pm.toImage().save(sys.argv[1], "ICO")
print("icon written" if ok else "icon write FAILED", sys.argv[1])
