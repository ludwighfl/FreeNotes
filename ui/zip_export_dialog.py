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


class ZipExportDialog(QDialog):
    """Dialog for choosing ZIP export mode."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bibliothek exportieren")
        self.setFixedSize(440, 300)
        self.setObjectName("zipExportDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)

        title = QLabel("Bibliothek exportieren")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff;")
        layout.addWidget(title)

        self._radio_pdf = QRadioButton(
            "Annotierte PDFs exportieren")
        self._radio_pdf.setChecked(True)
        self._radio_pdf.setStyleSheet("color: #cccccc;")
        self._radio_backup = QRadioButton(
            "Backup (.freenotes + .pdf)")
        self._radio_backup.setStyleSheet("color: #cccccc;")

        desc_pdf = QLabel(
            "Erstellt PDFs mit eingebetteten "
            "Annotationen \u2014 ideal zum Teilen.")
        desc_pdf.setStyleSheet(
            "color: #888888; font-size: 11px; "
            "margin-left: 20px;")
        desc_pdf.setWordWrap(True)

        desc_backup = QLabel(
            "Erstellt ein vollständiges Backup "
            "mit allen Rohdaten \u2014 ideal zum Archivieren.")
        desc_backup.setStyleSheet(
            "color: #888888; font-size: 11px; "
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

        self.setStyleSheet("""
            #zipExportDialog { background: #1e1e1e; }
            QPushButton {
                background: #333333; color: #cccccc;
                border: 1px solid #444; border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover { background: #444444; }
            #primaryBtn {
                background: #3B7BF5; color: #ffffff;
                border: none; font-weight: bold;
            }
            #primaryBtn:hover { background: #5090FF; }
        """)

    @property
    def mode(self) -> str:
        return "pdf" if self._radio_pdf.isChecked() else "backup"
