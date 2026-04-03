"""Fade animations for widget transitions."""

from __future__ import annotations

from PySide6.QtCore import (
    QObject,
    QPropertyAnimation,
    QEasingCurve,
)
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QStackedWidget,
    QWidget,
)


class FadeAnimation(QObject):
    """Fade-in a single widget.

    Sets a QGraphicsOpacityEffect, animates opacity 0→1,
    then removes the effect to avoid rendering overhead.

    Usage:
        FadeAnimation(widget, duration=180).start()
    """

    def __init__(
        self,
        widget: QWidget,
        duration: int = 180,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent or widget)
        self._widget = widget
        self._duration = duration
        self._anim: QPropertyAnimation | None = None

    def start(self) -> None:
        effect = QGraphicsOpacityEffect(self._widget)
        self._widget.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(self._duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(
            lambda: self._widget.setGraphicsEffect(None))
        anim.start(
            QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        # Hold reference to prevent GC
        self._anim = anim


class StackFadeTransition(QObject):
    """Fade-in transition for a QStackedWidget.

    Fades in the new page softly upon calling switch_to(index).
    Since QStackedWidget hides the old page immediately, this acts as 
    a smooth fade-in over the background color rather than a true crossfade.

    Usage:
        transition = StackFadeTransition(stack, duration=150)
        transition.switch_to(index)
    """

    def __init__(
        self,
        stack: QStackedWidget,
        duration: int = 150,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent or stack)
        self._stack = stack
        self._duration = duration
        self._anim: QPropertyAnimation | None = None

    def switch_to(self, index: int) -> None:
        if self._stack.currentIndex() == index:
            return

        target = self._stack.widget(index)
        if target is None:
            return

        # Cancel running animation
        if self._anim is not None:
            try:
                self._anim.stop()
            except RuntimeError:
                pass
            old = self._stack.currentWidget()
            if old:
                old.setGraphicsEffect(None)

        effect = QGraphicsOpacityEffect(target)
        target.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        self._stack.setCurrentIndex(index)

        self._anim = QPropertyAnimation(
            effect, b"opacity", self)
        self._anim.setDuration(self._duration)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(
            lambda: target.setGraphicsEffect(None))
        self._anim.start(
            QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
