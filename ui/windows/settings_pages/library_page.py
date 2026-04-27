"""Library settings page – annotations path and export."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QProgressDialog,
    QApplication,
)

from core.i18n import tr


class LibraryPage(QWidget):
    """Settings page for library path and export."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(self._make_title(tr("settings.tabs.library")))
        layout.addSpacing(24)

        # ── Current path ──
        layout.addWidget(self._make_label(tr("settings.library.path")))
        layout.addSpacing(8)

        from core.app_settings import AppSettings
        current = AppSettings.get_annotations_root()
        path_str = str(current) if current else tr("settings.library.not_set")

        self._path_label = QLabel(path_str)
        self._path_label.setObjectName("settingsPathLabel")
        self._path_label.setWordWrap(True)
        layout.addWidget(self._path_label)
        layout.addSpacing(10)

        change_btn = QPushButton(tr("settings.library.change_path"))
        change_btn.setObjectName("settingsActionBtn")
        change_btn.setFixedWidth(200)
        change_btn.clicked.connect(self._on_change_path)
        layout.addWidget(change_btn)
        layout.addSpacing(24)

        # ── Separator ──
        layout.addWidget(self._make_separator())
        layout.addSpacing(24)

        # ── Export ──
        layout.addWidget(self._make_label(tr("settings.library.export")))
        layout.addSpacing(8)

        export_pdf_btn = QPushButton(
            tr("settings.library.export_pdf"))
        export_pdf_btn.setObjectName("settingsActionBtn")
        export_pdf_btn.setFixedWidth(280)
        export_pdf_btn.clicked.connect(
            lambda: self._on_export("pdf"))
        layout.addWidget(export_pdf_btn)
        layout.addSpacing(8)

        export_backup_btn = QPushButton(
            tr("settings.library.export_backup"))
        export_backup_btn.setObjectName("settingsActionBtn")
        export_backup_btn.setFixedWidth(280)
        export_backup_btn.clicked.connect(
            lambda: self._on_export("backup"))
        layout.addWidget(export_backup_btn)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_change_path(self) -> None:
        from core.app_settings import AppSettings
        from core.library_manager import LibraryManager
        from app.app_state import AppState

        current = str(AppSettings.get_annotations_root() or "")
        chosen = QFileDialog.getExistingDirectory(
            self, tr("settings.library.choose_path"), current)
        if not chosen:
            return

        reply = QMessageBox.question(
            self,
            tr("settings.library.change_path_title"),
            tr("settings.library.change_path_msg").format(chosen),
            QMessageBox.StandardButton.Ok
            | QMessageBox.StandardButton.Cancel)
        if reply != QMessageBox.StandardButton.Ok:
            return

        new_root = Path(chosen)
        AppSettings.set_annotations_root(new_root)
        AppState().library_manager = LibraryManager(new_root)
        self._path_label.setText(chosen)

    def _on_export(self, mode: str) -> None:
        from app.app_state import AppState
        from core.zip_exporter import ZipExporter

        lm = AppState().library_manager
        if lm is None:
            QMessageBox.warning(
                self, tr("settings.library.no_library_title"),
                tr("settings.library.no_library_msg"))
            return

        target, _ = QFileDialog.getSaveFileName(
            self, tr("settings.library.save_zip"), "",
            "ZIP-Archiv (*.zip)")
        if not target:
            return
        if not target.endswith(".zip"):
            target += ".zip"

        progress = QProgressDialog(
            tr("settings.library.exporting"), tr("settings.library.cancel"), 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)
        progress.show()

        def on_progress(pct: int, name: str) -> None:
            progress.setValue(pct)
            progress.setLabelText(tr("settings.library.export_progress").format(name))
            QApplication.processEvents()

        exporter = ZipExporter(lm)
        try:
            if mode == "pdf":
                exporter.export_annotated_pdfs(
                    Path(target), on_progress)
            else:
                exporter.export_backup(
                    Path(target), on_progress)
            progress.close()
            QMessageBox.information(
                self, tr("settings.library.export_success"),
                tr("settings.library.zip_saved").format(target))
        except Exception as e:
            progress.close()
            QMessageBox.critical(
                self, tr("settings.library.export_failed"), str(e))

    # ------------------------------------------------------------------
    # Widget helpers
    # ------------------------------------------------------------------

    def _make_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        lbl.setObjectName("settingsPageTitle")
        return lbl

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("settingsLabel")
        return lbl

    @staticmethod
    def _make_separator() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("settingsSeparator")
        return sep
