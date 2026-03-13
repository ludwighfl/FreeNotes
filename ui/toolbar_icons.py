"""Toolbar icon helpers – color swatch and width dot icon creation."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap


def make_color_icon(color: str, size: int = 20, checked: bool = False) -> QIcon:
    """Create a circular color swatch icon, optionally with a checkmark.

    Args:
        color: Hex color string.
        size: Icon size in pixels.
        checked: If True, draw a white checkmark over the swatch.

    Returns:
        QIcon with a filled circle.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    if color.lower() in ("#ffffff", "#fff"):
        painter.setPen(QPen(QColor("#555555"), 1))
    else:
        painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)

    if checked:
        # Determine checkmark color: dark for light colors, white for dark
        c = QColor(color)
        luminance = 0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF()
        check_color = QColor("#1a1a1a") if luminance > 0.6 else QColor("#ffffff")
        painter.setPen(QPen(check_color, 2))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(0, 0, size, size, Qt.AlignmentFlag.AlignCenter, "✓")

    painter.end()
    return QIcon(pixmap)


def make_width_icon(dot_radius: int, size: int = 24) -> QIcon:
    """Create an icon showing a filled circle representing pen width.

    Args:
        dot_radius: Radius of the filled dot.
        size: Icon size in pixels.

    Returns:
        QIcon with a centered dot.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#cccccc"))
    painter.setPen(Qt.PenStyle.NoPen)
    cx = size // 2
    cy = size // 2
    painter.drawEllipse(cx - dot_radius, cy - dot_radius, dot_radius * 2, dot_radius * 2)
    painter.end()
    return QIcon(pixmap)
