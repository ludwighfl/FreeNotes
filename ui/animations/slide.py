"""Slide-down animation for expanding folder items."""

from __future__ import annotations

from PySide6.QtCore import (
    QObject,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
)
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QWidget,
)


class SlideDownAnimation(QObject):
    """Slide-down + fade-in for a list of widgets.

    Widgets start at maximumHeight=0 and animate to target_height,
    while simultaneously fading opacity 0→1.

    Usage:
        SlideDownAnimation(
            widgets=new_items, target_height=32,
        ).start()
    """

    def __init__(
        self,
        widgets: list[QWidget],
        target_height: int = 32,
        delay_ms: int = 20,
        duration: int = 150,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._widgets = list(widgets)
        self._target_height = target_height
        self._delay_ms = delay_ms
        self._duration = duration
        self._anims: list = []

    def start(self) -> None:
        for i, widget in enumerate(self._widgets):
            # Initial state: height 0, opacity 0
            widget.setMaximumHeight(0)
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)

            delay = i * self._delay_ms
            QTimer.singleShot(
                delay,
                lambda w=widget, ef=effect: self._slide_in(w, ef))

    def _slide_in(
        self,
        widget: QWidget,
        effect: QGraphicsOpacityEffect,
    ) -> None:
        # Animate height
        anim_h = QPropertyAnimation(
            widget, b"maximumHeight", widget)
        anim_h.setDuration(self._duration)
        anim_h.setStartValue(0)
        anim_h.setEndValue(self._target_height)
        anim_h.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_h.start(
            QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anims.append(anim_h)

        # Simultaneously animate opacity
        anim_o = QPropertyAnimation(
            effect, b"opacity", widget)
        anim_o.setDuration(self._duration)
        anim_o.setStartValue(0.0)
        anim_o.setEndValue(1.0)
        anim_o.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_o.finished.connect(
            lambda w=widget: w.setGraphicsEffect(None))
        anim_o.start(
            QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anims.append(anim_o)
