"""Stagger fade-in animation for lists of widgets."""

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


class StaggerFadeAnimation(QObject):
    """Fade in a list of widgets one after another.

    Each widget starts invisible, then fades in with
    a staggered delay of i * delay_ms (capped at max_total_ms).

    Usage:
        StaggerFadeAnimation(
            widgets=cards, delay_ms=30, duration=200,
        ).start()
    """

    def __init__(
        self,
        widgets: list[QWidget],
        delay_ms: int = 30,
        duration: int = 200,
        max_total_ms: int = 600,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._widgets = list(widgets)
        self._delay_ms = delay_ms
        self._duration = duration
        self._max_total_ms = max_total_ms
        self._anims: list[QPropertyAnimation] = []

    def start(self) -> None:
        # Set all widgets initially invisible
        for widget in self._widgets:
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)

        # Schedule staggered fade-ins
        for i, widget in enumerate(self._widgets):
            delay = min(i * self._delay_ms, self._max_total_ms)
            QTimer.singleShot(
                delay, lambda w=widget: self._fade_in(w))

    def _fade_in(self, widget: QWidget) -> None:
        effect = widget.graphicsEffect()
        if effect is None:
            return

        anim = QPropertyAnimation(effect, b"opacity", widget)
        anim.setDuration(self._duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(
            lambda w=widget: w.setGraphicsEffect(None))
        anim.start(
            QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anims.append(anim)
