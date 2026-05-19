"""Background hover fade animation for QWidgets."""

from __future__ import annotations

from PySide6.QtCore import QObject, QPropertyAnimation, QEasingCurve, Qt, Property
from PySide6.QtGui import QColor, QPainter, QBrush
from PySide6.QtWidgets import QWidget


class HoverOverlayWidget(QWidget):
    """Semi-transparent child overlay that draws a smooth background on hover.
    
    WA_TransparentForMouseEvents ensures that this widget is completely
    invisible to mouse clicks and hover events, meaning all mouse events
    propagate directly to the parent widget.
    """
    def __init__(self, parent: QWidget, border_radius: int = 6) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._border_radius = border_radius
        self._alpha = 0
        self._color = QColor(255, 255, 255)
        self.hide()

    def get_alpha(self) -> int:
        return self._alpha

    def set_alpha(self, alpha: int) -> None:
        self._alpha = alpha
        if alpha > 0:
            self.show()
        else:
            self.hide()
        self.update()

    # Define a Qt Property so QPropertyAnimation can animate this value
    alpha = Property(int, get_alpha, set_alpha)

    def paintEvent(self, event) -> None:
        if self._alpha <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Blend current animated alpha with base color
        color = QColor(self._color)
        color.setAlpha(self._alpha)
        
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), self._border_radius, self._border_radius)


class BackgroundFadeHoverEffect(QObject):
    """Installs a smooth background fade overlay on any widget.
    
    Usage:
        self._hover_effect = BackgroundFadeHoverEffect(
            widget=self,
            hover_color=QColor(255, 255, 255, 25), # low alpha to avoid blocking icon/text
            duration=150,
            border_radius=6
        )
    """
    def __init__(
        self,
        widget: QWidget,
        hover_color: QColor,
        duration: int = 150,
        border_radius: int = 6,
    ) -> None:
        super().__init__(widget)
        self._widget = widget
        self._hover_color = hover_color
        self._duration = duration
        
        # Create overlay as a child of the target widget
        self._overlay = HoverOverlayWidget(widget, border_radius)
        self._overlay._color = QColor(hover_color.red(), hover_color.green(), hover_color.blue())
        self._target_alpha = hover_color.alpha()
        
        # Ensure overlay starts with the correct geometry
        self._overlay.setGeometry(self._widget.rect())
        
        # Install event filter to capture enter, leave, and resize events
        widget.installEventFilter(self)
        
        self._anim = QPropertyAnimation(self._overlay, b"alpha", self)
        self._anim.setDuration(duration)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def eventFilter(self, watched: QObject, event) -> bool:
        if watched is self._widget:
            import PySide6.QtCore as QtCore
            if event.type() == QtCore.QEvent.Type.Enter:
                self._anim.stop()
                self._anim.setStartValue(self._overlay.get_alpha())
                self._anim.setEndValue(self._target_alpha)
                self._anim.start()
            elif event.type() == QtCore.QEvent.Type.Leave:
                self._anim.stop()
                self._anim.setStartValue(self._overlay.get_alpha())
                self._anim.setEndValue(0)
                self._anim.start()
            elif event.type() == QtCore.QEvent.Type.Resize:
                self._overlay.setGeometry(self._widget.rect())
        return super().eventFilter(watched, event)
