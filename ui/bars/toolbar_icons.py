"""Toolbar icon helpers – color swatch and width dot icon creation."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

_color_icon_cache: dict[tuple, QIcon] = {}
_width_icon_cache: dict[tuple, QIcon] = {}


def make_color_icon(color: str, size: int = 20, checked: bool = False) -> QIcon:
    """Create a circular color swatch icon, optionally with a checkmark."""
    key = (color.lower(), size, checked)
    if key in _color_icon_cache:
        return _color_icon_cache[key]
    
    # NEU: Skalierungsfaktor für High-DPI (3 deckt Monitore bis 300% Skalierung scharf ab)
    scale_factor = 3
    
    # NEU: Das Pixmap wird physisch größer angelegt (z.B. 60x60 Pixel)
    pixmap = QPixmap(size * scale_factor, size * scale_factor)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    # NEU: Wir sagen dem Pixmap, dass es hochauflösend ist. 
    # Dadurch verhält es sich für den Painter und den Button weiterhin wie ein 20x20 Bild!
    pixmap.setDevicePixelRatio(scale_factor)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # NEU: TextAntialiasing hinzugefügt, damit das Häkchen butterweich gerendert wird
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing) 
    
    painter.setBrush(QColor(color))
    
    if color.lower() in ("#ffffff", "#fff"):
        painter.setPen(QPen(QColor("#555555"), 1))
    else:
        painter.setPen(Qt.PenStyle.NoPen)
        
    # Deine Koordinaten bleiben unverändert, Qt skaliert sie dank devicePixelRatio automatisch!
    painter.drawEllipse(1, 1, size - 2, size - 2)

    if checked:
        c = QColor(color)
        luminance = 0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF()
        check_color = QColor("#1a1a1a") if luminance > 0.6 else QColor("#ffffff")
        
        # Pen-Dicke bleibt bei 2 (logischen) Pixeln
        painter.setPen(QPen(check_color, 2))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, "✓")

    painter.end()
    icon = QIcon(pixmap)
    _color_icon_cache[key] = icon
    return icon


def make_width_icon(dot_radius: int, size: int = 24) -> QIcon:
    """Create an icon showing a filled circle representing pen width."""
    key = (dot_radius, size)
    if key in _width_icon_cache:
        return _width_icon_cache[key]
    
    # NEU: Der bewährte Skalierungsfaktor
    scale_factor = 3
    
    # NEU: Das physische Pixmap wird 3-mal so groß angelegt (z.B. 72x72)
    pixmap = QPixmap(size * scale_factor, size * scale_factor)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    # NEU: Das Pixmap auf die logische Größe (z.B. 24x24) stauchen
    pixmap.setDevicePixelRatio(scale_factor)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    painter.setBrush(QColor("#cccccc"))
    painter.setPen(Qt.PenStyle.NoPen)
    
    # Deine Berechnungen bleiben exakt gleich! Qt malt den Kreis nun
    # intern mit 3-facher Präzision.
    cx = size // 2
    cy = size // 2
    painter.drawEllipse(cx - dot_radius, cy - dot_radius, dot_radius * 2, dot_radius * 2)
    
    painter.end()
    icon = QIcon(pixmap)
    _width_icon_cache[key] = icon
    return icon
