"""Custom circular color chip button with custom paintEvent to bypass OS-specific rendering issues."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QToolButton, QWidget
from core.app_settings import AppSettings


class ColorChipButton(QToolButton):
    """Custom circular color chip button with custom paintEvent."""
    
    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.color_hex: str = color
        self.setFixedSize(28, 28)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hovered: bool = False
        self.pressed: bool = False

    def enterEvent(self, event) -> None:
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.pressed = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.pressed = False
            self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        is_light = AppSettings.get_theme() == "light"
        
        # 1. Paint the outer hover / checked / pressed ring
        outer_rect = self.rect().adjusted(1, 1, -1, -1)
        
        if self.isChecked():
            # Checked outline (solid white/dark)
            pen_color = QColor("#333333") if is_light else QColor("#ffffff")
            painter.setPen(QPen(pen_color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(outer_rect)
        elif self.hovered:
            # Hover outline (semi-transparent white/dark)
            pen_color = QColor(0, 0, 0, 64) if is_light else QColor(255, 255, 255, 115)
            painter.setPen(QPen(pen_color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(outer_rect)
            
        # 2. Paint the inner color swatch circle
        inner_rect = self.rect().adjusted(5, 5, -5, -5)
        
        c = QColor(self.color_hex)
        painter.setBrush(c)
        
        # Border around white swatch so it's visible on light backgrounds
        if self.color_hex.lower() in ("#ffffff", "#fff"):
            painter.setPen(QPen(QColor("#bbbbbb") if is_light else QColor("#555555"), 1))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            
        painter.drawEllipse(inner_rect)
        
        # 3. Draw a clean, antialiased checkmark ✓ in the center if checked
        if self.isChecked():
            luminance = 0.299 * c.redF() + 0.587 * c.greenF() + 0.114 * c.blueF()
            check_color = QColor("#1a1a1a") if luminance > 0.6 else QColor("#ffffff")
            painter.setPen(QPen(check_color, 2))
            painter.setFont(QFont("Roboto", 9, QFont.Weight.Bold))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "✓")
            
        painter.end()
