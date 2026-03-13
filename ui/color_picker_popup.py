"""Color picker popup – compact frameless popup with HSV wheel and sliders."""

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QColor, QFont, QPainter, QRegion, QPainterPath
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QApplication,
)

from ui.color_wheel_widget import ColorWheelWidget


class ColorPickerPopup(QWidget):
    """Compact frameless popup with HSV color wheel and S/V sliders.

    Uses an opaque background with rounded-corner mask instead of
    WA_TranslucentBackground to avoid Windows rendering issues.
    """

    POPUP_WIDTH: int = 300
    CORNER_RADIUS: int = 12
    BG_COLOR: str = "#1e1e1e"

    color_selected = Signal(QColor)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setFixedWidth(self.POPUP_WIDTH)

        # Flag to prevent signal loops
        self._updating: bool = False

        # --- Layout ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 18)
        layout.setSpacing(10)

        # 1. Header: "Farbe"
        title = QLabel("Farbe")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(title)

        # 2. "Farbton" label + wheel
        hue_label = QLabel("Farbton")
        hue_label.setFont(QFont("Segoe UI", 11))
        hue_label.setStyleSheet("color: #888888; background: transparent;")
        layout.addWidget(hue_label)

        self._wheel = ColorWheelWidget()
        self._wheel.setFixedHeight(200)
        self._wheel.setMinimumSize(200, 200)
        layout.addWidget(self._wheel)

        # 3. "Sättigung" label + slider
        sat_label = QLabel("Sättigung")
        sat_label.setFont(QFont("Segoe UI", 11))
        sat_label.setStyleSheet("color: #888888; background: transparent;")
        layout.addWidget(sat_label)

        self._saturation_slider = QSlider(Qt.Orientation.Horizontal)
        self._saturation_slider.setRange(0, 100)
        self._saturation_slider.setValue(100)
        self._saturation_slider.setObjectName("satSlider")
        self._saturation_slider.setFixedHeight(22)
        layout.addWidget(self._saturation_slider)

        # 4. "Helligkeit" label + slider
        val_label = QLabel("Helligkeit")
        val_label.setFont(QFont("Segoe UI", 11))
        val_label.setStyleSheet("color: #888888; background: transparent;")
        layout.addWidget(val_label)

        self._value_slider = QSlider(Qt.Orientation.Horizontal)
        self._value_slider.setRange(0, 100)
        self._value_slider.setValue(100)
        self._value_slider.setObjectName("valSlider")
        self._value_slider.setFixedHeight(22)
        layout.addWidget(self._value_slider)

        # --- Connections ---
        self._wheel.color_changed.connect(self._on_wheel_color_changed)
        self._saturation_slider.valueChanged.connect(self._on_saturation_changed)
        self._value_slider.valueChanged.connect(self._on_value_changed)

        # Initial gradient
        self._update_slider_gradients()

    # ------------------------------------------------------------------
    # Painting & rounded corners
    # ------------------------------------------------------------------

    def paintEvent(self, event: object) -> None:
        """Draw opaque rounded background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.BG_COLOR))
        painter.drawRoundedRect(
            self.rect(), self.CORNER_RADIUS, self.CORNER_RADIUS
        )
        painter.end()

    def resizeEvent(self, event: object) -> None:
        """Apply rounded-corner mask on resize."""
        path = QPainterPath()
        path.addRoundedRect(
            0.0, 0.0, float(self.width()), float(self.height()),
            float(self.CORNER_RADIUS), float(self.CORNER_RADIUS),
        )
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        super().resizeEvent(event)

    # ------------------------------------------------------------------
    # Slot handlers
    # ------------------------------------------------------------------

    def _on_wheel_color_changed(self, color: QColor) -> None:
        if self._updating:
            return
        self._updating = True
        self._saturation_slider.setValue(int(self._wheel.saturation * 100))
        self._value_slider.setValue(int(self._wheel.value * 100))
        self._update_slider_gradients()
        self.color_selected.emit(self._wheel.current_color)
        self._updating = False

    def _on_saturation_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._wheel.saturation = value / 100.0
        self._update_slider_gradients()
        self.color_selected.emit(self._wheel.current_color)
        self._updating = False

    def _on_value_changed(self, value: int) -> None:
        if self._updating:
            return
        self._updating = True
        self._wheel.value = value / 100.0
        self._update_slider_gradients()
        self.color_selected.emit(self._wheel.current_color)
        self._updating = False

    # ------------------------------------------------------------------
    # Slider gradients
    # ------------------------------------------------------------------

    def _update_slider_gradients(self) -> None:
        h = self._wheel.hue
        s = self._wheel.saturation
        v = self._wheel.value

        sat_end = QColor.fromHsvF(h / 360.0, 1.0, max(v, 0.3))
        self._saturation_slider.setStyleSheet(
            f"QSlider#satSlider::groove:horizontal {{"
            f"  height: 6px; border-radius: 3px;"
            f"  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"  stop:0 #666666, stop:1 {sat_end.name()});"
            f"}}"
            f"QSlider#satSlider::handle:horizontal {{"
            f"  width: 16px; height: 16px; margin: -5px 0;"
            f"  border-radius: 8px; background: white;"
            f"  border: 1px solid rgba(255,255,255,0.2);"
            f"}}"
            f"QSlider#satSlider::sub-page:horizontal {{ background: transparent; }}"
        )

        val_end = QColor.fromHsvF(h / 360.0, s, 1.0)
        self._value_slider.setStyleSheet(
            f"QSlider#valSlider::groove:horizontal {{"
            f"  height: 6px; border-radius: 3px;"
            f"  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"  stop:0 #000000, stop:1 {val_end.name()});"
            f"}}"
            f"QSlider#valSlider::handle:horizontal {{"
            f"  width: 16px; height: 16px; margin: -5px 0;"
            f"  border-radius: 8px; background: white;"
            f"  border: 1px solid rgba(255,255,255,0.2);"
            f"}}"
            f"QSlider#valSlider::sub-page:horizontal {{ background: transparent; }}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_color(self, color: QColor) -> None:
        """Set all widgets to the given color without emitting signals."""
        self._updating = True
        h, s, v, _ = color.getHsvF()
        if h < 0:
            h = 0.0
        self._wheel.set_hsv(int(h * 360), s, v)
        self._saturation_slider.setValue(int(s * 100))
        self._value_slider.setValue(int(v * 100))
        self._update_slider_gradients()
        self._updating = False

    def show_at(self, global_pos: QPoint) -> None:
        """Show popup near global_pos, clamped to screen edges."""
        self.adjustSize()
        screen = QApplication.primaryScreen()
        if screen:
            sr = screen.availableGeometry()
            x = min(global_pos.x(), sr.right() - self.width() - 8)
            y = global_pos.y()
            if y + self.height() > sr.bottom():
                y = global_pos.y() - self.height() - 40
            x = max(x, sr.left() + 8)
            self.move(x, y)
        else:
            self.move(global_pos)
        self.show()
