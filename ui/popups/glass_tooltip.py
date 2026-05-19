"""Glassmorphic custom tooltip – replaces native QToolTip with a frosted-glass popup.

The key architectural insight: we construct the tooltip widget *once* with the
correct window flags (FramelessWindowHint, NoDropShadowWindowHint,
WA_TranslucentBackground).  We never call setWindowFlags() during a show event,
which avoids the native-handle recreation loop that froze the app previously.

The companion ``GlassTooltipFilter`` intercepts ``QEvent.ToolTip`` on every
widget *before* Qt creates the native tooltip, suppresses it, and shows our
custom glass widget instead.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QPoint, QEvent, QObject, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont, QFontMetrics
from PySide6.QtWidgets import QWidget, QApplication


class GlassToolTip(QWidget):
    """Singleton frosted-glass tooltip that matches GlassMenu aesthetics."""

    _instance: GlassToolTip | None = None

    @classmethod
    def instance(cls) -> GlassToolTip:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        super().__init__(None)

        # --- Window flags set at construction (safe, no recreation loop) ---
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._text: str = ""
        self._font = QFont("Segoe UI", 9, QFont.Weight.Medium)
        self._padding_h = 12
        self._padding_v = 6
        self._radius = 6

        # Auto-hide timer (matches native tooltip behaviour)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_tip(self, global_pos: QPoint, text: str, timeout_ms: int = 3000) -> None:
        """Display the tooltip near *global_pos* with the given *text*."""
        if not text:
            self.hide()
            return

        self._text = text

        # Measure required size
        fm = QFontMetrics(self._font)
        text_rect = fm.boundingRect(
            0, 0, 300, 1000,
            Qt.TextFlag.TextWordWrap | int(Qt.AlignmentFlag.AlignLeft),
            self._text,
        )
        w = text_rect.width() + 2 * self._padding_h + 2
        h = text_rect.height() + 2 * self._padding_v + 2

        self.setFixedSize(w, h)

        # Position: slightly below and to the right of cursor
        tip_pos = global_pos + QPoint(12, 20)

        # Keep on screen
        screen = QApplication.screenAt(global_pos)
        if screen:
            geo = screen.availableGeometry()
            if tip_pos.x() + w > geo.right():
                tip_pos.setX(geo.right() - w - 4)
            if tip_pos.y() + h > geo.bottom():
                tip_pos.setY(global_pos.y() - h - 6)

        self.move(tip_pos)
        self.show()
        self.raise_()

        self._hide_timer.start(timeout_ms)

    # ------------------------------------------------------------------
    # Painting – frosted glass capsule
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:
        from core.app_settings import AppSettings
        is_light = AppSettings.get_theme() == "light"

        if is_light:
            bg = QColor(250, 250, 250, 225)
            border = QColor(0, 0, 0, 22)
            text_color = QColor("#333333")
        else:
            bg = QColor(30, 30, 30, 225)
            border = QColor(255, 255, 255, 25)
            text_color = QColor("#e0e0e0")

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Rounded rect path
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                            self._radius, self._radius)

        # Background fill
        painter.fillPath(path, bg)

        # Border
        painter.setPen(QPen(border, 1.0))
        painter.drawPath(path)

        # Text
        painter.setPen(text_color)
        painter.setFont(self._font)
        text_rect = self.rect().adjusted(
            self._padding_h, self._padding_v,
            -self._padding_h, -self._padding_v,
        )
        painter.drawText(text_rect,
                         Qt.TextFlag.TextWordWrap | int(Qt.AlignmentFlag.AlignLeft) | int(Qt.AlignmentFlag.AlignVCenter),
                         self._text)
        painter.end()


class GlassTooltipFilter(QObject):
    """Application-level event filter that replaces native tooltips with GlassToolTip.

    Install on QApplication::instance() in main.py.  Intercepts QEvent.ToolTip
    *before* Qt creates the native tooltip widget, so no window-flag mutation
    happens on an already-visible widget.
    """

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            widget = watched
            if isinstance(widget, QWidget):
                text = widget.toolTip()
                if text:
                    GlassToolTip.instance().show_tip(event.globalPos(), text)
                else:
                    GlassToolTip.instance().hide()
                return True  # suppress native tooltip
        # Hide tooltip on mouse-move away, click, key press etc.
        if event.type() in (
            QEvent.Type.Leave,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.KeyPress,
            QEvent.Type.FocusOut,
            QEvent.Type.WindowDeactivate,
        ):
            tip = GlassToolTip._instance
            if tip is not None and tip.isVisible():
                tip.hide()
        return super().eventFilter(watched, event)
