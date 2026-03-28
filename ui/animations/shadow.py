"""Shadow hover animation for PdfCard."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QWidget,
)


class ShadowHoverAnimation(QObject):
    """Animate a QGraphicsDropShadowEffect on hover via manual lerp.

    blurRadius and color are not Q_PROPERTYs, so we use a
    QTimer-based lerp instead of QPropertyAnimation.

    Usage:
        self._shadow_anim = ShadowHoverAnimation(widget=self)
        # In enterEvent: self._shadow_anim.hover_enter()
        # In leaveEvent: self._shadow_anim.hover_leave()
    """

    STEP_INTERVAL_MS: int = 15
    LERP_FACTOR: float = 0.25
    SNAP_THRESHOLD: float = 0.5

    def __init__(
        self,
        widget: QWidget,
        blur_default: int = 8,
        blur_hover: int = 20,
        offset_default: int = 2,
        offset_hover: int = 6,
        alpha_default: int = 80,
        alpha_hover: int = 140,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent or widget)
        self._widget = widget

        self._blur_default = float(blur_default)
        self._blur_hover = float(blur_hover)
        self._offset_default = float(offset_default)
        self._offset_hover = float(offset_hover)
        self._alpha_default = float(alpha_default)
        self._alpha_hover = float(alpha_hover)

        # Target values (start at defaults)
        self._target_blur = self._blur_default
        self._target_offset = self._offset_default
        self._target_alpha = self._alpha_default

        # Create shadow effect
        self._shadow = QGraphicsDropShadowEffect(widget)
        self._shadow.setBlurRadius(blur_default)
        self._shadow.setOffset(0, offset_default)
        self._shadow.setColor(QColor(0, 0, 0, alpha_default))
        widget.setGraphicsEffect(self._shadow)

        # Lerp timer
        self._timer = QTimer(self)
        self._timer.setInterval(self.STEP_INTERVAL_MS)
        self._timer.timeout.connect(self._step)

    def hover_enter(self) -> None:
        self._target_blur = self._blur_hover
        self._target_offset = self._offset_hover
        self._target_alpha = self._alpha_hover
        self._timer.start()

    def hover_leave(self) -> None:
        self._target_blur = self._blur_default
        self._target_offset = self._offset_default
        self._target_alpha = self._alpha_default
        self._timer.start()

    def _step(self) -> None:
        try:
            # Check if C++ object is alive and still attached
            self._shadow.blurRadius()
            if self._widget.graphicsEffect() is not self._shadow:
                raise RuntimeError("Effect replaced")
        except RuntimeError:
            # Re-create if deleted by another animation (e.g. StaggerFade)
            if self._widget.graphicsEffect() is not None:
                # Another effect is currently running; abort our timer
                self._timer.stop()
                return
            self._shadow = QGraphicsDropShadowEffect(self._widget)
            self._shadow.setBlurRadius(self._blur_default)
            self._shadow.setOffset(0, self._offset_default)
            self._shadow.setColor(QColor(0, 0, 0, int(self._alpha_default)))
            self._widget.setGraphicsEffect(self._shadow)

        t = self.LERP_FACTOR

        cur_blur = self._shadow.blurRadius()
        cur_offset = self._shadow.yOffset()
        cur_alpha = self._shadow.color().alpha()

        new_blur = cur_blur + (self._target_blur - cur_blur) * t
        new_offset = cur_offset + (self._target_offset - cur_offset) * t
        new_alpha = cur_alpha + (self._target_alpha - cur_alpha) * t

        self._shadow.setBlurRadius(new_blur)
        self._shadow.setOffset(0, new_offset)
        self._shadow.setColor(QColor(0, 0, 0, int(new_alpha)))

        # Stop when close enough to target
        thr = self.SNAP_THRESHOLD
        if (abs(new_blur - self._target_blur) < thr
                and abs(new_offset - self._target_offset) < thr
                and abs(new_alpha - self._target_alpha) < 1.0):
            self._shadow.setBlurRadius(self._target_blur)
            self._shadow.setOffset(0, self._target_offset)
            self._shadow.setColor(
                QColor(0, 0, 0, int(self._target_alpha)))
            self._timer.stop()
