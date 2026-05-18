"""Shimmer effect animation for skeleton loading."""

from PySide6.QtCore import Qt, QTimer, QObject
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QPaintEvent
from PySide6.QtWidgets import QWidget


class ShimmerOverlay(QWidget):
    """A widget that displays an animated shimmer gradient over its parent."""

    def __init__(self, parent: QWidget, border_radius: int = 4) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(parent.size())
        self._border_radius = border_radius

        self._offset = -0.5
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(16)  # ~60fps
        
        # Track parent resize
        if parent:
            parent.installEventFilter(self)

    def _step(self) -> None:
        self._offset += 0.04
        if self._offset > 1.5:
            self._offset = -0.5
        self.update()

    def eventFilter(self, obj: QObject, event: object) -> bool:
        """Keep size in sync with parent."""
        if obj == self.parent() and event.type() == event.Type.Resize:
            self.resize(obj.size())
        return super().eventFilter(obj, event)

    def paintEvent(self, event: QPaintEvent) -> None:
        from core.app_settings import AppSettings
        is_light = AppSettings.get_theme() == "light"

        base_c = QColor(220, 220, 220) if is_light else QColor(45, 45, 45)
        shimmer_c = QColor(245, 245, 245) if is_light else QColor(60, 60, 60)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        w, h = self.width(), self.height()
        
        # Diagonal gradient for a better shimmer look
        grad = QLinearGradient(0, 0, w, h)
        
        pos = self._offset
        grad.setColorAt(max(0.0, min(1.0, pos - 0.2)), base_c)
        grad.setColorAt(max(0.0, min(1.0, pos)), shimmer_c)
        grad.setColorAt(max(0.0, min(1.0, pos + 0.2)), base_c)

        painter.setBrush(grad)
        painter.drawRoundedRect(0, 0, w, h, self._border_radius, self._border_radius)
        
    def stop(self) -> None:
        self._timer.stop()
        if self.parent():
            self.parent().removeEventFilter(self)
        self.deleteLater()
