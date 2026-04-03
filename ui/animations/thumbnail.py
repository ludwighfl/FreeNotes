"""Fade-In Animation für lazy gerenderte Thumbnails."""

from __future__ import annotations

from PySide6.QtCore import (
    QObject,
    QPropertyAnimation,
    QEasingCurve,
)
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QLabel,
)


class ThumbnailFadeAnimation(QObject):
    """Blendet ein Thumbnail-Label sanft ein.

    Wird aufgerufen sobald ein Thumbnail lazy
    gerendert und in ein QLabel gesetzt wurde.
    Ist idempotent: zweites start() auf demselben
    Widget (Re-Render nach Invalidierung)
    überspringt die Animation.

    Verwendung:
        ThumbnailFadeAnimation(
            label=self._thumb_label,
            duration=200,
        ).start()
    """

    _FADED_IN_ATTR = "_thumb_fade_done"

    def __init__(
        self,
        label: QLabel,
        duration: int = 200,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._label    = label
        self._duration = duration

    def start(self) -> None:
        # Bereits animiert -> direkt setzen, kein zweites Fade:
        if getattr(self._label,
                   self._FADED_IN_ATTR,
                   False):
            return

        setattr(self._label,
                self._FADED_IN_ATTR, True)

        effect = QGraphicsOpacityEffect(
            self._label)
        self._label.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        anim = QPropertyAnimation(
            effect, b"opacity",
            self._label)
        anim.setDuration(self._duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(
            QEasingCurve.Type.OutCubic)
        def safe_unset():
            try:
                self._label.graphicsEffect()
                self._label.setGraphicsEffect(None)
            except RuntimeError:
                pass
                
        anim.finished.connect(safe_unset)
        anim.start(
            QPropertyAnimation
            .DeletionPolicy.DeleteWhenStopped)
        self._anim = anim
