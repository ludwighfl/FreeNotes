"""Smooth scroll animation for QGraphicsView."""

from PySide6.QtCore import QObject, QVariantAnimation, QEasingCurve, QPointF, Signal
from PySide6.QtWidgets import QGraphicsView


class ScrollAnimation(QObject):
    """Animates the viewport's center position for smooth navigation."""

    finished = Signal()

    def __init__(self, view: QGraphicsView, duration: int = 500, parent: QObject = None) -> None:
        super().__init__(parent or view)
        self._view = view
        self._duration = duration
        
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(self._duration)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_value_changed)
        self._anim.finished.connect(self.finished.emit)

    def scroll_to(self, target_point: QPointF) -> None:
        """Animate scroll to the given scene point."""
        self._anim.stop()
        
        # Determine current center in scene coordinates
        viewport_rect = self._view.viewport().rect()
        current_center = self._view.mapToScene(viewport_rect.center())
        
        self._anim.setStartValue(current_center)
        self._anim.setEndValue(target_point)
        self._anim.start()

    def _on_value_changed(self, value: QPointF) -> None:
        """Update view center during animation."""
        self._view.centerOn(value)

    def is_running(self) -> bool:
        """Check if the animation is currently active."""
        return self._anim.state() == QVariantAnimation.State.Running
