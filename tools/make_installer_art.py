"""Draw the installer wizard images (BMP) from the app icon: make_installer_art.py <out_dir>"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QLinearGradient, QColor, QFont

app = QGuiApplication([])
import icons

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
icon = icons.app_icon()


def side(w, h, path):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    g = QLinearGradient(0, 0, 0, h)
    g.setColorAt(0, QColor("#2f6fed"))
    g.setColorAt(1, QColor("#16337a"))
    p.fillRect(0, 0, w, h, g)
    s = w * 0.62
    p.drawPixmap(int((w - s) / 2), int(h * 0.20), icon.pixmap(256, 256).scaled(int(s), int(s), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", 1)
    f.setPixelSize(int(w * 0.17))
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, h * 0.20 + s + h * 0.03, w, w * 0.25), Qt.AlignmentFlag.AlignCenter, "LitePDF")
    p.end()
    img.save(path, "BMP")


def small(n, path):
    img = QImage(n, n, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawPixmap(0, 0, icon.pixmap(256, 256).scaled(n, n, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    p.end()
    img.save(path, "BMP")


side(164, 314, os.path.join(out, "wizard-164.bmp"))
side(328, 628, os.path.join(out, "wizard-328.bmp"))
small(55, os.path.join(out, "small-55.bmp"))
small(110, os.path.join(out, "small-110.bmp"))
print("wizard images written to", out)
