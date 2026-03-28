"""Display settings page – theme toggle and default font size."""

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

from ui.components.icon_factory import IconFactory


class DisplayPage(QWidget):
    """Settings page for display options (theme, font size)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── Title ──
        layout.addWidget(self._make_title("Anzeige"))
        layout.addSpacing(24)

        # ── Dark / Light Mode ──
        layout.addWidget(self._make_label("Design"))
        layout.addSpacing(8)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)

        from core.app_settings import AppSettings
        current = AppSettings.get_theme()

        self._dark_btn = self._make_mode_btn("moon", "Dark Mode")
        self._light_btn = self._make_mode_btn("sun", "Light Mode")
        self._dark_btn.setChecked(current == "dark")
        self._light_btn.setChecked(current == "light")

        self._dark_btn.clicked.connect(
            lambda: self._set_theme("dark"))
        self._light_btn.clicked.connect(
            lambda: self._set_theme("light"))

        mode_row.addWidget(self._dark_btn)
        mode_row.addWidget(self._light_btn)
        mode_row.addStretch()
        layout.addLayout(mode_row)
        layout.addSpacing(6)

        hint_row = QHBoxLayout()
        hint_row.setSpacing(6)
        hint_icon = QLabel()
        hint_icon.setPixmap(
            IconFactory.create_pixmap(
                "info", color="#5577cc", size=14))
        hint_icon.setFixedSize(14, 14)
        hint_icon.setStyleSheet("background: transparent;")
        hint_row.addWidget(hint_icon)
        hint_text = QLabel(
            "Ein Neustart ist für die vollständige "
            "Anwendung des Designs erforderlich.")
        hint_text.setStyleSheet("color: #555555; font-size: 11px;")
        hint_text.setWordWrap(True)
        hint_row.addWidget(hint_text, 1)
        layout.addLayout(hint_row)
        layout.addSpacing(24)

        # ── Separator ──
        layout.addWidget(self._make_separator())
        layout.addSpacing(24)

        # ── Default font size ──
        layout.addWidget(
            self._make_label("Standard-Schriftgröße (Textbox)"))
        layout.addSpacing(8)

        size_row = QHBoxLayout()
        from ui.popups.font_size_widget import FontSizeWidget
        self._font_size = FontSizeWidget()
        self._font_size.setValue(
            AppSettings.get_default_font_size())
        self._font_size.valueChanged.connect(
            self._on_font_size_changed)
        size_row.addWidget(self._font_size)

        size_hint = QLabel("pt")
        size_hint.setStyleSheet("color: #888888; font-size: 13px;")
        size_row.addWidget(size_hint)
        size_row.addStretch()
        layout.addLayout(size_row)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _set_theme(self, theme: str) -> None:
        from core.app_settings import AppSettings
        AppSettings.set_theme(theme)
        self._dark_btn.setChecked(theme == "dark")
        self._light_btn.setChecked(theme == "light")
        # Reload QSS immediately
        from PySide6.QtWidgets import QApplication
        from styles.loader import load_stylesheet
        app = QApplication.instance()
        if app:
            app.setStyleSheet(load_stylesheet())

    def _on_font_size_changed(self, size: int) -> None:
        from core.app_settings import AppSettings
        from app.app_state import AppState
        AppSettings.set_default_font_size(size)
        if hasattr(AppState(), "default_font_size"):
            AppState().default_font_size = size

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

    @staticmethod
    def _make_mode_btn(icon_name: str, label: str) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("modeBtn")
        btn.setCheckable(True)
        btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setIcon(
            IconFactory.create(icon_name, color="#cccccc", size=16))
        btn.setIconSize(QSize(16, 16))
        btn.setText(f"  {label}")
        btn.setFixedHeight(36)
        btn.setMinimumWidth(140)
        return btn
