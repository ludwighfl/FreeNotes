"""Custom HSV color wheel widget – painted entirely via QPainter."""

import math

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QPainter,
    QPen,
    QBrush,
    QFont,
    QPainterPath,
)
from PySide6.QtWidgets import QWidget, QSizePolicy


class ColorWheelWidget(QWidget):
    """HSV color wheel with draggable hue ring and center preview.

    The outer ring shows all hues (0–360°). A white handle on the ring
    indicates the current hue. The inner circle previews the full
    color (hue + saturation + value). A reset icon in the center
    returns to the default color (green, H=120).
    """

    # Ring geometry as ratios of half-widget-size
    RING_OUTER_RATIO: float = 0.95
    RING_INNER_RATIO: float = 0.72
    HANDLE_RADIUS: int = 8
    RESET_ICON_RADIUS: int = 20

    # Default color (pure green)
    DEFAULT_HUE: int = 120
    DEFAULT_SAT: float = 1.0
    DEFAULT_VAL: float = 1.0

    color_changed = Signal(QColor)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._hue: int = self.DEFAULT_HUE
        self._saturation: float = self.DEFAULT_SAT
        self._value: float = self.DEFAULT_VAL

        self._dragging_ring: bool = False
        self._dragging_center: bool = False

        self.setMinimumSize(260, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def hue(self) -> int:
        return self._hue

    @hue.setter
    def hue(self, value: int) -> None:
        self._hue = int(value) % 360
        self.update()

    @property
    def saturation(self) -> float:
        return self._saturation

    @saturation.setter
    def saturation(self, value: float) -> None:
        self._saturation = max(0.0, min(1.0, value))
        self.update()

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, value: float) -> None:
        self._value = max(0.0, min(1.0, value))
        self.update()

    @property
    def current_color(self) -> QColor:
        """The full HSV color from current hue, saturation, and value."""
        return QColor.fromHsvF(self._hue / 360.0, self._saturation, self._value)

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _center(self) -> QPointF:
        return QPointF(self.width() / 2.0, self.height() / 2.0)

    def _outer_radius(self) -> float:
        return min(self.width(), self.height()) / 2.0 * self.RING_OUTER_RATIO

    def _inner_radius(self) -> float:
        return self._outer_radius() * (self.RING_INNER_RATIO / self.RING_OUTER_RATIO)

    def _handle_pos(self) -> QPointF:
        """Position of the hue handle on the ring."""
        center = self._center()
        mid_radius = (self._outer_radius() + self._inner_radius()) / 2.0
        angle_rad = math.radians(90 - self._hue)
        return QPointF(
            center.x() + mid_radius * math.cos(angle_rad),
            center.y() - mid_radius * math.sin(angle_rad),
        )

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        center = self._center()
        outer_r = self._outer_radius()
        inner_r = self._inner_radius()

        # --- Step 1: Hue ring via conical gradient ---
        gradient = QConicalGradient(center, 90.0)  # Start at top (12 o'clock)
        num_stops = 13
        for i in range(num_stops):
            h = i / (num_stops - 1)
            gradient.setColorAt(h, QColor.fromHsvF(h, 1.0, 1.0))

        # Draw outer filled circle with gradient
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(center, outer_r, outer_r)

        # Punch inner hole with background color
        painter.setBrush(QColor("#1a1a1a"))
        painter.drawEllipse(center, inner_r, inner_r)

        # --- Step 2: Inner preview circle ---
        preview_r = inner_r - 6.0
        preview_color = self.current_color
        painter.setBrush(preview_color)
        # Darker border
        border_color = QColor.fromHsvF(
            self._hue / 360.0,
            self._saturation,
            max(0.0, self._value * 0.7),
        )
        painter.setPen(QPen(border_color, 3))
        painter.drawEllipse(center, preview_r, preview_r)

        # --- Step 3: Reset icon in center ---
        painter.setPen(QPen(QColor(255, 255, 255, 180), 0))
        reset_font = QFont("Segoe UI", 20)
        painter.setFont(reset_font)
        icon_rect = QRectF(
            center.x() - 20, center.y() - 16, 40, 32
        )
        painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "↩")

        # --- Step 4: Handle on the hue ring ---
        handle_pos = self._handle_pos()
        # Shadow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 60))
        painter.drawEllipse(handle_pos, self.HANDLE_RADIUS + 1, self.HANDLE_RADIUS + 1)
        # Handle fill
        handle_color = QColor.fromHsvF(self._hue / 360.0, 1.0, 1.0)
        painter.setBrush(handle_color)
        painter.setPen(QPen(QColor("#ffffff"), 2.5))
        painter.drawEllipse(handle_pos, self.HANDLE_RADIUS, self.HANDLE_RADIUS)

        painter.end()

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: object) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        pos = event.position()
        center = self._center()
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        dist = math.sqrt(dx * dx + dy * dy)

        inner_r = self._inner_radius()
        outer_r = self._outer_radius()

        if inner_r <= dist <= outer_r:
            # Clicked on hue ring
            self._dragging_ring = True
            self._update_hue(pos)
        elif dist < self.RESET_ICON_RADIUS:
            # Clicked reset icon
            self._hue = self.DEFAULT_HUE
            self._saturation = self.DEFAULT_SAT
            self._value = self.DEFAULT_VAL
            self.update()
            self.color_changed.emit(self.current_color)
        elif dist < inner_r:
            self._dragging_center = True

    def mouseMoveEvent(self, event: object) -> None:
        if self._dragging_ring:
            self._update_hue(event.position())

    def mouseReleaseEvent(self, event: object) -> None:
        self._dragging_ring = False
        self._dragging_center = False

    def _update_hue(self, pos: QPointF) -> None:
        """Compute hue from mouse position angle relative to center."""
        center = self._center()
        dx = pos.x() - center.x()
        dy = center.y() - pos.y()  # Y inverted for math convention
        angle_deg = math.degrees(math.atan2(dy, dx))
        self._hue = int(90 - angle_deg) % 360
        self.update()
        self.color_changed.emit(self.current_color)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_hsv(self, hue: int, saturation: float, value: float) -> None:
        """Set all HSV values without emitting signal (to avoid loops).

        Args:
            hue: Hue 0–359.
            saturation: Saturation 0.0–1.0.
            value: Value/brightness 0.0–1.0.
        """
        self._hue = int(hue) % 360
        self._saturation = max(0.0, min(1.0, saturation))
        self._value = max(0.0, min(1.0, value))
        self.update()
