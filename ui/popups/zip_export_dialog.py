"""Dialog for choosing ZIP export mode."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QDialog,
    QRadioButton,
)

from core.app_settings import AppSettings


from ui.popups.glass_dialog import GlassDialog


class ZipExportDialog(GlassDialog):
    """Dialog for choosing ZIP export mode."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bibliothek exportieren")
        self.setFixedSize(440, 340)
        self.setObjectName("zipExportDialog")

        is_light = AppSettings.get_theme() == "light"
        title_color = "#1a1a1a" if is_light else "#ffffff"
        text_color = "#333333" if is_light else "#cccccc"
        desc_color = "#666666" if is_light else "#888888"
        
        btn_bg = "#ffffff" if is_light else "#333333"
        btn_text = "#1a1a1a" if is_light else "#cccccc"
        btn_border = "#d0d0d0" if is_light else "#444444"
        btn_hover_bg = "#e8e8e8" if is_light else "#444444"

        layout = self._content_layout
        layout.setSpacing(12)

        title = QLabel("Bibliothek exportieren")
        title.setFont(QFont("Roboto", 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {title_color};")
        layout.addWidget(title)

        self._radio_pdf = QRadioButton(
            "Annotierte PDFs exportieren")
        self._radio_pdf.setChecked(True)
        self._radio_pdf.setStyleSheet(f"color: {text_color};")
        self._radio_backup = QRadioButton(
            "Backup (.freenotes + .pdf)")
        self._radio_backup.setStyleSheet(f"color: {text_color};")

        desc_pdf = QLabel(
            "Erstellt PDFs mit eingebetteten "
            "Annotationen \u2014 ideal zum Teilen.")
        desc_pdf.setStyleSheet(
            f"color: {desc_color}; font-size: 11px; "
            "margin-left: 20px;")
        desc_pdf.setWordWrap(True)

        desc_backup = QLabel(
            "Erstellt ein vollständiges Backup "
            "mit allen Rohdaten \u2014 ideal zum Archivieren.")
        desc_backup.setStyleSheet(
            f"color: {desc_color}; font-size: 11px; "
            "margin-left: 20px;")
        desc_backup.setWordWrap(True)

        layout.addWidget(self._radio_pdf)
        layout.addWidget(desc_pdf)
        layout.addWidget(self._radio_backup)
        layout.addWidget(desc_backup)
        layout.addStretch()

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        export_btn = QPushButton("Exportieren …")
        export_btn.setObjectName("primaryBtn")
        export_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(export_btn)
        layout.addLayout(btn_row)

        self.setStyleSheet(f"""
            #zipExportDialog {{ background: transparent; }}
            QRadioButton {{ color: {text_color}; }}
            QPushButton {{
                background: {btn_bg}; color: {btn_text};
                border: 1px solid {btn_border}; border-radius: 4px;
                padding: 6px 16px;
            }}
            QPushButton:hover {{ background: {btn_hover_bg}; }}
            #primaryBtn {{
                background: #3B7BF5; color: #ffffff;
                border: none; font-weight: bold;
            }}
            #primaryBtn:hover {{ background: #5090FF; }}
        """)

    @property
    def mode(self) -> str:
        return "pdf" if self._radio_pdf.isChecked() else "backup"
