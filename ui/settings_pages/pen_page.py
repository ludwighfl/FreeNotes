"""Pen settings page – default color and width."""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QToolButton,
)


class PenPage(QWidget):
    """Settings page for pen defaults (color, width)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── Title ──
        layout.addWidget(self._make_title("Stift"))
        layout.addSpacing(24)

        # ── Default color ──
        layout.addWidget(self._make_label("Standard-Farbe"))
        layout.addSpacing(8)

        from core.app_settings import AppSettings
        from ui.toolbar_icons import make_color_icon

        saved_colors = AppSettings.get_pen_colors()
        current_color = AppSettings.get_pen_default_color()

        color_row = QHBoxLayout()
        color_row.setSpacing(6)
        self._color_btns: list[QToolButton] = []
        self._colors = saved_colors

        for i, color in enumerate(saved_colors):
            btn = QToolButton()
            btn.setIcon(make_color_icon(
                color, checked=(color == current_color)))
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(28, 28)
            btn.setCheckable(True)
            btn.setChecked(color == current_color)
            btn.setObjectName("colorChip")
            btn.clicked.connect(
                lambda checked, c=color, idx=i:
                    self._on_color_selected(c, idx))
            color_row.addWidget(btn)
            self._color_btns.append(btn)

        color_row.addStretch()
        layout.addLayout(color_row)
        layout.addSpacing(24)

        # ── Separator ──
        layout.addWidget(self._make_separator())
        layout.addSpacing(24)

        # ── Default width ──
        layout.addWidget(self._make_label("Standard-Breite"))
        layout.addSpacing(8)

        from ui.toolbar_icons import make_width_icon
        self._widths = [1.0, 2.0, 4.0, 8.0, 14.0]
        self._radii = [1, 2, 4, 6, 8]
        saved_width = AppSettings.get_pen_width()

        width_row = QHBoxLayout()
        width_row.setSpacing(6)
        self._width_btns: list[QToolButton] = []

        for i, (w, r) in enumerate(
                zip(self._widths, self._radii)):
            btn = QToolButton()
            btn.setIcon(make_width_icon(r))
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(28, 28)
            btn.setCheckable(True)
            btn.setChecked(abs(w - saved_width) < 0.1)
            btn.setObjectName("widthBtn")
            btn.clicked.connect(
                lambda checked, ww=w:
                    self._on_width_selected(ww))
            width_row.addWidget(btn)
            self._width_btns.append(btn)

        width_row.addStretch()
        layout.addLayout(width_row)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_color_selected(self, color: str, idx: int) -> None:
        from core.app_settings import AppSettings
        from app.app_state import AppState
        from PySide6.QtGui import QColor
        from ui.toolbar_icons import make_color_icon

        AppSettings.set_pen_default_color(color)
        AppState().tool_style.color = QColor(color)

        for i, btn in enumerate(self._color_btns):
            btn.setChecked(i == idx)
            btn.setIcon(make_color_icon(
                self._colors[i], checked=(i == idx)))

    def _on_width_selected(self, width: float) -> None:
        from core.app_settings import AppSettings
        from app.app_state import AppState

        AppSettings.set_pen_width(width)
        AppState().tool_style.width = width

        for i, btn in enumerate(self._width_btns):
            btn.setChecked(abs(self._widths[i] - width) < 0.1)

    # ------------------------------------------------------------------
    # Widget helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #ffffff;")
        return lbl

    @staticmethod
    def _make_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #aaaaaa; font-size: 13px;")
        return lbl

    @staticmethod
    def _make_separator() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("settingsSeparator")
        return sep
