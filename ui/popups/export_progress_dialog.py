"""Export progress and completion dialog with frosted-glass styling."""

from __future__ import annotations

import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
)

from ui.popups.glass_dialog import GlassDialog
from ui.components.icon_factory import IconFactory
from core.i18n import tr
from core.app_settings import AppSettings
from app.app_state import AppState


class ExportProgressDialog(GlassDialog):
    """Frosted-glass dialog that displays PDF export progress and completion message in a single unified window."""

    def __init__(self, target_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._target_path = target_path
        self._filename = os.path.basename(target_path)

        self.setWindowTitle(tr("settings.library.export", "Export"))
        self.setFixedSize(420, 200)
        self.setObjectName("exportProgressDialog")

        layout = self._content_layout
        layout.setSpacing(14)

        # Header Row: Icon + Text
        header_row = QHBoxLayout()
        header_row.setSpacing(14)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(32, 32)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        header_row.addWidget(self._icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        self._status_title = QLabel(tr("viewer.export_progress", "PDF wird exportiert …"))
        self._status_title.setFont(QFont("Roboto", 11, QFont.Weight.Bold))
        text_col.addWidget(self._status_title)

        self._detail_label = QLabel(self._filename)
        self._detail_label.setFont(QFont("Roboto", 9))
        self._detail_label.setWordWrap(True)
        text_col.addWidget(self._detail_label)

        header_row.addLayout(text_col, 1)
        layout.addLayout(header_row)

        # Progress Section
        self._progress_section = QVBoxLayout()
        self._progress_section.setSpacing(6)

        pct_row = QHBoxLayout()
        pct_row.addStretch()
        self._pct_label = QLabel("0%")
        self._pct_label.setFont(QFont("Roboto", 9, QFont.Weight.Bold))
        pct_row.addWidget(self._pct_label)
        self._progress_section.addLayout(pct_row)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        self._progress_section.addWidget(self._progress_bar)

        layout.addLayout(self._progress_section)
        layout.addStretch()

        # Button Row (hidden until completion/error)
        self._btn_row = QHBoxLayout()
        self._btn_row.addStretch()

        self._ok_btn = QPushButton(tr("dialog.button.ok", "OK"))
        self._ok_btn.setObjectName("primaryBtn")
        self._ok_btn.setFixedSize(90, 32)
        self._ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ok_btn.clicked.connect(self.accept)
        self._ok_btn.setVisible(False)
        self._btn_row.addWidget(self._ok_btn)

        layout.addLayout(self._btn_row)

        self._set_state_exporting()
        self._update_theme_styles()
        AppState().theme_updated.connect(self._update_theme_styles)

    def _set_state_exporting(self) -> None:
        self._icon_label.setPixmap(
            IconFactory.create_pixmap("download", color="#3B7BF5", size=32)
        )
        self._status_title.setText(tr("viewer.export_progress", "PDF wird exportiert …"))
        self._detail_label.setText(self._filename)
        self._progress_section.setEnabled(True)
        self._ok_btn.setVisible(False)

    def set_progress(self, pct: int) -> None:
        """Update progress bar percentage."""
        clamped = max(0, min(100, pct))
        self._progress_bar.setValue(clamped)
        self._pct_label.setText(f"{clamped}%")

    def set_success(self) -> None:
        """Transition dialog to success state in-place."""
        self.set_progress(100)
        self._icon_label.setPixmap(
            IconFactory.create_pixmap("check_circle", color="#10B981", size=32)
        )
        self._status_title.setText(tr("settings.library.export_success", "Export erfolgreich"))
        
        # Display localized "*file-name* wurde erfolgreich exportiert."
        success_msg = tr("viewer.export_success_msg", "„{filename}“ wurde erfolgreich exportiert.").format(
            filename=self._filename
        )
        self._detail_label.setText(success_msg)
        
        self._ok_btn.setVisible(True)
        self._ok_btn.setFocus()

    def set_error(self, error_text: str) -> None:
        """Transition dialog to error state in-place."""
        self._icon_label.setPixmap(
            IconFactory.create_pixmap("alert_triangle", color="#EF4444", size=32)
        )
        self._status_title.setText(tr("settings.library.export_failed", "Export fehlgeschlagen"))
        self._detail_label.setText(error_text)
        self._ok_btn.setVisible(True)
        self._ok_btn.setFocus()

    def _update_theme_styles(self) -> None:
        is_light = AppSettings.get_theme() == "light"
        title_color = "#1a1a1a" if is_light else "#ffffff"
        text_color = "#555555" if is_light else "#aaaaaa"
        bar_bg = "#e5e7eb" if is_light else "#374151"

        self._status_title.setStyleSheet(f"color: {title_color}; background: transparent;")
        self._detail_label.setStyleSheet(f"color: {text_color}; background: transparent;")
        self._pct_label.setStyleSheet(f"color: #3B7BF5; background: transparent;")

        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {bar_bg};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: #3B7BF5;
                border-radius: 4px;
            }}
        """)

        self._ok_btn.setStyleSheet("""
            QPushButton#primaryBtn {
                background-color: #3B7BF5;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton#primaryBtn:hover {
                background-color: #2563EB;
            }
            QPushButton#primaryBtn:pressed {
                background-color: #1D4ED8;
            }
        """)
