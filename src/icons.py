"""Tiny inline SVG icon set (stroke icons, recoloured for light/dark theme)."""
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "save": '<path d="M5 3h11l3 3v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
            '<path d="M7 3v5h8V3"/><path d="M7 21v-7h10v7"/>',
    "print": '<path d="M7 9V3h10v6"/><rect x="3" y="9" width="18" height="8" rx="2"/>'
             '<path d="M7 14h10v7H7z"/>',
    "undo": '<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    "redo": '<path d="M15 14l5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h3"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l5 5"/>',
    "up": '<path d="M6 15l6-6 6 6"/>',
    "down": '<path d="M6 9l6 6 6-6"/>',
    "left": '<path d="M15 6l-6 6 6 6"/>',
    "right": '<path d="M9 6l6 6-6 6"/>',
    "zoom_in": '<path d="M5 12h14M12 5v14"/>',
    "zoom_out": '<path d="M5 12h14"/>',
    "fit_width": '<path d="M3 12h18M7 8l-4 4 4 4M17 8l4 4-4 4"/>',
    "fit_page": '<rect x="6" y="3" width="12" height="18" rx="1.5"/>',
    "rotate": '<path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v5h-5"/>',
    "moon": '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/>',
    "sidebar": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "select": '<path d="M5 3l14 7-6.5 2L10 19z"/>',
    "highlight": '<path d="M15 4l5 5-9 9H7l-2-2v-3z"/><path d="M4 21h8" stroke-width="3"/>',
    "underline": '<path d="M7 4v7a5 5 0 0 0 10 0V4"/><path d="M5 21h14"/>',
    "strike": '<path d="M16.5 7.5C16 5.5 14.3 4.5 12 4.5c-2.5 0-4.2 1.2-4.2 3 0 1.6 1.2 2.3 4.2 3"/>'
              '<path d="M4 12h16"/><path d="M8 17c.4 1.8 2 2.7 4.2 2.7 2.5 0 4.2-1.2 4.2-3 0-.8-.3-1.4-.9-1.9"/>',
    "note": '<path d="M4 4h16v11l-5 5H4z"/><path d="M15 20v-5h5"/><path d="M8 9h8M8 13h4"/>',
    "text": '<path d="M5 7V4h14v3M12 4v16M9 20h6"/>',
    "sign": '<path d="M4 20l1-4L16 5l3 3L8 19z"/><path d="M14 7l3 3"/><path d="M13 21h8"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "check": '<path d="M5 12l5 5 9-10"/>',
    "plus": '<path d="M5 12h14M12 5v14"/>',
    "newwin": '<rect x="3" y="6" width="14" height="14" rx="2"/><path d="M9 3h12v12"/>',
}

_cache = {}


def app_icon() -> QIcon:
    """Blue rounded page with a pen stroke - drawn in code, no asset files needed."""
    from PySide6.QtCore import QRectF, QPointF
    from PySide6.QtGui import QColor, QPen, QPainterPath
    ic = QIcon()
    for px in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(px, px)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = px / 64.0
        p.scale(s, s)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2f6fed"))
        p.drawRoundedRect(QRectF(4, 2, 56, 60), 10, 10)
        p.setBrush(QColor("white"))
        p.drawRoundedRect(QRectF(14, 11, 36, 42), 4, 4)
        p.setBrush(QColor("#ffd23f"))
        p.drawRect(QRectF(19, 19, 26, 6))
        p.setBrush(QColor("#c5cbd6"))
        p.drawRect(QRectF(19, 30, 26, 3))
        p.drawRect(QRectF(19, 36, 18, 3))
        pen = QPen(QColor("#2f6fed"), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        path = QPainterPath(QPointF(19, 47))
        path.cubicTo(25, 41, 28, 51, 33, 45)
        path.cubicTo(36, 42, 39, 48, 45, 44)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()
        ic.addPixmap(pm)
    return ic


def icon(name: str, color: str = "#333333") -> QIcon:
    key = (name, color)
    if key in _cache:
        return _cache[key]
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        f"{PATHS[name]}</svg>"
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    ic = QIcon()
    for px in (16, 20, 24, 32, 48):
        pm = QPixmap(px, px)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(p)
        p.end()
        ic.addPixmap(pm)
    _cache[key] = ic
    return ic
