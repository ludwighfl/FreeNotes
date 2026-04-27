"""Language settings page – UI language selection."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QApplication,
)

from ui.components.icon_factory import IconFactory
from core.i18n import tr


class LanguagePage(QWidget):
    """Settings page for language selection."""

    LANGUAGES: list[tuple[str, str, str]] = [
        ("de", "DE", "Deutsch"),
        ("en", "GB", "English"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._make_title(tr("settings.tabs.language")))
        layout.addSpacing(16)

        desc = QLabel(tr("settings.language.desc"))
        desc.setObjectName("settingsLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addSpacing(20)

        from core.app_settings import AppSettings
        current = AppSettings.get_language()

        self._lang_btns: dict[str, QToolButton] = {}

        for code, badge_text, label in self.LANGUAGES:
            btn = QToolButton()
            btn.setObjectName("langBtn")
            btn.setCheckable(True)
            btn.setChecked(code == current)
            btn.setFixedHeight(44)
            btn.setMinimumWidth(250)
            btn.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setIcon(QIcon(self._make_badge(badge_text)))
            btn.setIconSize(QSize(28, 18))
            btn.setText(f"  {label}")

            btn.clicked.connect(
                lambda checked, c=code: self._on_language_selected(c))
            layout.addWidget(btn)
            layout.addSpacing(8)
            self._lang_btns[code] = btn

        layout.addSpacing(16)

        # Info hint with Lucide icon
        hint_row = QHBoxLayout()
        hint_row.setSpacing(6)
        hint_icon = QLabel()
        hint_icon.setPixmap(
            IconFactory.create_pixmap(
                "info", color="#5577cc", size=14))
        hint_icon.setFixedSize(14, 14)
        hint_icon.setObjectName("settingsHintIcon")
        hint_row.addWidget(hint_icon)
        hint_text = QLabel(tr("settings.language.restart_hint"))
        hint_text.setObjectName("settingsHintText")
        hint_text.setWordWrap(True)
        hint_row.addWidget(hint_text, 1)
        layout.addLayout(hint_row)
        layout.addStretch()

    # ------------------------------------------------------------------

    @staticmethod
    def _make_badge(text: str) -> QPixmap:
        """Create a crisp text badge pixmap (e.g. 'DE', 'GB')."""
        app = QApplication.instance()
        dpr = 2.0
        if app is not None:
            screen = app.primaryScreen()
            if screen is not None:
                dpr = max(screen.devicePixelRatio(), 2.0)

        w, h = 28, 18
        pw, ph = int(w * dpr), int(h * dpr)

        pm = QPixmap(pw, ph)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(
            QPainter.RenderHint.TextAntialiasing, True)

        from core.app_settings import AppSettings
        is_light = AppSettings.get_theme() == "light"
        bg_color = "#e0e0e0" if is_light else "#3a3a3a"
        text_color = "#555555" if is_light else "#aaaaaa"

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg_color))
        painter.drawRoundedRect(QRectF(0, 0, w, h), 3, 3)

        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(text_color))
        painter.drawText(
            QRectF(0, 0, w, h),
            Qt.AlignmentFlag.AlignCenter,
            text)
        painter.end()
        return pm

    def _on_language_selected(self, code: str) -> None:
        from core.app_settings import AppSettings
        AppSettings.set_language(code)
        for c, btn in self._lang_btns.items():
            btn.setChecked(c == code)

    def _make_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        lbl.setObjectName("settingsPageTitle")
        return lbl

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("settingsLabel")
        return lbl
