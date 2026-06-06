"""App settings page – app reset functionality."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QApplication,
)

from core.i18n import tr
from core.app_settings import AppSettings
from ui.popups.custom_dialogs import CustomMessageBox


class AppPage(QWidget):
    """Settings page for app-level configurations."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._make_title(tr("settings.tabs.app")))
        layout.addSpacing(24)

        # Danger zone
        danger_title = QLabel(tr("settings.app.reset_title"))
        danger_title.setFont(QFont("Roboto", 12, QFont.Weight.Bold))
        danger_title.setObjectName("settingsDangerTitle")
        layout.addWidget(danger_title)
        layout.addSpacing(8)

        desc = QLabel(tr("settings.app.reset_desc"))
        desc.setObjectName("settingsLabel")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addSpacing(16)

        reset_btn = QPushButton(tr("settings.app.reset_btn"))
        reset_btn.setObjectName("settingsDangerBtn")
        reset_btn.clicked.connect(self._on_reset_clicked)
        layout.addWidget(reset_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()

    def _make_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Roboto", 15, QFont.Weight.Bold))
        lbl.setObjectName("settingsPageTitle")
        return lbl

    def _on_reset_clicked(self) -> None:
        """Prompt confirmation and clear all settings."""
        reply = CustomMessageBox.warning(
            self,
            tr("settings.app.reset_confirm_title"),
            tr("settings.app.reset_confirm_msg"),
            CustomMessageBox.StandardButton.Yes | CustomMessageBox.StandardButton.No,
            CustomMessageBox.StandardButton.No
        )
        if reply == CustomMessageBox.StandardButton.Yes:
            # Clear QSettings
            AppSettings._get().clear()
            
            # Restart or exit
            QApplication.quit()
