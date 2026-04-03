"""Splash screen – banner logo with a modern spinning loader underneath.

The spinner is drawn as a simple QPainter arc that rotates via QTimer.
paintEvent cost is ~1 ms (background fill + drawPixmap + drawArc), making
the animation immune to main-thread load.
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QKeyEvent, QGuiApplication,
)


class SplashScreen(QWidget):
    """Full-screen splash overlay with a spinning loader below the logo."""

    CYCLE_DURATION_MS = 2500   # one full spinner revolution
    SPINNER_FPS = 60
    SPINNER_SIZE = 32          # logical pixels
    SPINNER_THICKNESS = 3      # pen width in logical pixels
    SPINNER_GAP_PX = 28       # gap between banner bottom and spinner center

    def __init__(self, image_path: str, parent: QWidget | None = None):
        super().__init__(parent)
        
        # Make this a standalone, frameless top-level window
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.SplashScreen
        )
        self.resize(500, 300)
        
        self.bg_color = QColor("#1a1a1a")
        self.logical_width = 0
        self.logical_height = 0
        self.pixmap = QPixmap()

        original = QPixmap(image_path)
        if not original.isNull():
            screen = QGuiApplication.primaryScreen()
            
            # Center the splash screen on the primary monitor
            screen_geom = screen.geometry()
            self.move(
                (screen_geom.width() - self.width()) // 2,
                (screen_geom.height() - self.height()) // 2
            )
            
            target_w = screen_geom.width() * 0.20
            self.dpr = screen.devicePixelRatio()
            physical_w = int(target_w * self.dpr)

            self.pixmap = original.scaledToWidth(
                physical_w, Qt.TransformationMode.SmoothTransformation,
            )
            self.logical_width = self.pixmap.width() / self.dpr
            self.logical_height = self.pixmap.height() / self.dpr

        # Indeterminate spinner state
        self._head = 0.0          # the leading edge angle
        self._span = 30.0         # current arc length
        self._expanding = True    # whether the arc is growing or shrinking

        # Timer – NOT started until start_animation() is called
        interval = max(1, 1000 // self.SPINNER_FPS)
        self._timer = QTimer(self)
        self._timer.setInterval(interval)
        self._timer.timeout.connect(self._advance)

    # ------------------------------------------------------------------
    # Playback control
    # ------------------------------------------------------------------

    def start_animation(self) -> None:
        """Start the spinner animation."""
        if not self._timer.isActive():
            self._timer.start()

    def stop_animation(self) -> None:
        """Stop the spinner to free CPU."""
        self._timer.stop()

    def _advance(self) -> None:
        """Advance the spinner head and oscillate its length to create a modern tail-catch effect."""
        # Head always moves steadily clockwise (negative in Qt)
        self._head = (self._head - 5.0) % 360.0

        # Oscillate the arc length
        if self._expanding:
            self._span += 3.5
            if self._span >= 270.0:
                self._span = 270.0
                self._expanding = False
        else:
            self._span -= 3.5
            if self._span <= 30.0:
                self._span = 30.0
                self._expanding = True

        self.repaint()

    # ------------------------------------------------------------------
    # Painting – trivially fast
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:                # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self.bg_color)

        if self.logical_width == 0:
            p.end()
            return

        # --- Banner (centered) ---
        bx = (self.width() - self.logical_width) / 2.0
        by = (self.height() - self.logical_height) / 2.0 - self.SPINNER_GAP_PX
        p.drawPixmap(
            QRectF(bx, by, self.logical_width, self.logical_height),
            self.pixmap,
            QRectF(self.pixmap.rect()),
        )

        # --- Spinner (below banner, centered) ---
        cx = self.width() / 2.0
        cy = by + self.logical_height + self.SPINNER_GAP_PX
        r = self.SPINNER_SIZE / 2.0
        spinner_rect = QRectF(cx - r, cy - r, self.SPINNER_SIZE, self.SPINNER_SIZE)

        pen = QPen(QColor(255, 255, 255, 200))
        pen.setWidthF(self.SPINNER_THICKNESS)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)

        # Draw the arc
        # Qt draws from 'start' counter-clockwise for positive span, clockwise for negative.
        # So we draw clockwise from the tail angle.
        tail = self._head + self._span
        start_16 = int(tail * 16)
        span_16 = int(-self._span * 16)
        
        p.drawArc(spinner_rect, start_16, span_16)

        p.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        super().keyPressEvent(event)
