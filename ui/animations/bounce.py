"""Bounce animation for tool buttons."""

from __future__ import annotations

from PySide6.QtCore import (
    QObject,
    QPropertyAnimation,
    QEasingCurve,
    QSize,
)
from PySide6.QtWidgets import QToolButton


class BounceAnimation(QObject):
    """Bounces the iconSize of a QToolButton.

    Usage:
        BounceAnimation(btn, base_size=QSize(22, 22), peak_size=QSize(28, 28)).start()
    """

    def __init__(
        self,
        widget: QToolButton,
        base_size: QSize = QSize(22, 22),
        peak_size: QSize = QSize(28, 28),
        duration: int = 250,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent or widget)
        self._widget = widget
        self._base_size = base_size
        self._peak_size = peak_size
        self._duration = duration
        self._anim: QPropertyAnimation | None = None

    def start(self) -> None:
        # Cancel any existing animation to prevent conflicts
        if getattr(self._widget, "_bounce_anim", None) is not None:
            try:
                self._widget._bounce_anim.stop()
            except RuntimeError:
                pass

        anim = QPropertyAnimation(self._widget, b"iconSize", self)
        anim.setDuration(self._duration)
        
        # Keyframes for a pop-out and spring-back effect
        anim.setKeyValueAt(0.0, self._base_size)
        anim.setKeyValueAt(0.4, self._peak_size)
        anim.setKeyValueAt(1.0, self._base_size)
        
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._widget._bounce_anim = anim
        self._anim = anim
