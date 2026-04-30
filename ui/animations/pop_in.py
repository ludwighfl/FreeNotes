"""Pop-in animations for floating UI elements."""

from __future__ import annotations

from PySide6.QtCore import (
    QObject,
    QPropertyAnimation,
    QEasingCurve,
    QRect,
    QParallelAnimationGroup,
)
from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect


class PopInAnimation(QObject):
    """Animates a widget scaling/sliding up and fading in.

    Usage:
        PopInAnimation(widget).start()
    """

    def __init__(
        self,
        widget: QWidget,
        duration: int = 200,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent or widget)
        self._widget = widget
        self._duration = duration
        self._anim_group: QParallelAnimationGroup | None = None

    def start(self) -> None:
        # Prevent overlapping animations
        if getattr(self._widget, "_popin_anim", None) is not None:
            try:
                self._widget._popin_anim.stop()
            except RuntimeError:
                pass

        target_rect = self._widget.geometry()
        
        # Start a bit lower
        start_rect = QRect(
            target_rect.x(), target_rect.y() + 10, target_rect.width(), target_rect.height()
        )

        self._widget.setGeometry(start_rect)

        # Effect for opacity
        effect = QGraphicsOpacityEffect(self._widget)
        self._widget.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        # Opacity animation
        opacity_anim = QPropertyAnimation(effect, b"opacity")
        opacity_anim.setDuration(self._duration)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Geometry animation
        geom_anim = QPropertyAnimation(self._widget, b"geometry")
        geom_anim.setDuration(self._duration)
        geom_anim.setStartValue(start_rect)
        geom_anim.setEndValue(target_rect)
        geom_anim.setEasingCurve(QEasingCurve.Type.OutBack)  # Spring effect

        self._anim_group = QParallelAnimationGroup(self)
        self._anim_group.addAnimation(opacity_anim)
        self._anim_group.addAnimation(geom_anim)
        
        self._anim_group.finished.connect(
            lambda: self._widget.setGraphicsEffect(None)
        )
        
        self._widget._popin_anim = self._anim_group
        self._anim_group.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
