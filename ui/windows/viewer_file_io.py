"""Viewer file I/O mixin – handles loading, saving, and exporting documents."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog, QApplication

from core import undo_stack
from core.freenotes_store import FreenotesStore
from core.pdf_exporter import PdfExporter

if TYPE_CHECKING:
    from app.app_state import AppState
    from core.document_manager import DocumentManager
    from ui.page_scene import PageScene
    from ui.sidebar_widget import SidebarWidget
    from ui.three_dot_menu import ThreeDotMenu
    from PySide6.QtWidgets import QLabel, QLineEdit


class ViewerFileIOMixin:
    """Mixin for ViewerWindow to handle file operations (Load, Save, Export).

    Expects the host class to provide:
        _app_state: AppState
        _doc_manager: DocumentManager
        _page_scene: PageScene
        _sidebar: SidebarWidget
        _three_dot_menu: ThreeDotMenu
        _title_label: QLabel
        _ext_label: QLabel
        _breadcrumb_label: QLabel
        _total_pages_label: QLabel
        _page_input: QLineEdit
        _toolbar: ToolbarWidget
        _page_view: PageView
        _on_tool_changed(): method
    """

    def open_pdf(self, path: Path, auto_load_freenotes: bool = True) -> None:
        """Open a PDF file in the viewer.
        
        Args:
            path: Path to the PDF file.
            auto_load_freenotes: If True, search for and load matching .freenotes file.
        """
        from PySide6.QtGui import QIntValidator

        if not self._doc_manager.open_document(path):
            return

        page_count = self._doc_manager.get_page_count()
        self._app_state.current_pdf_path = path
        self._app_state.total_pages = page_count
        self._app_state.current_page = 0
        self._app_state.zoom_factor = 1.0

        self._title_label.setText(path.stem)
        self._ext_label.setText(".pdf")
        self._breadcrumb_label.setText(f"  {path.parent.name}")

        self._total_pages_label.setText(str(page_count))
        self._page_input.setValidator(QIntValidator(1, page_count, self))
        self._page_input.setText("1")
        
        self._page_scene.load_document(self._doc_manager)

        # Check if corresponding .freenotes exists and load it automatically
        freenotes_path = path.with_suffix(".freenotes")
        if auto_load_freenotes and freenotes_path.exists():
            try:
                _, structural_modified = FreenotesStore.load(
                    path=str(freenotes_path), scene=self._page_scene, doc_manager=self._doc_manager)
                if structural_modified:
                    page_count = self._doc_manager.get_page_count()
                    self._app_state.total_pages = page_count
                    self._total_pages_label.setText(str(page_count))
                    self._page_input.setValidator(QIntValidator(1, page_count, self))
                self._app_state.freenotes_path = str(freenotes_path)
                self._sidebar.load_document(self._doc_manager, self._page_scene)
                self._sidebar.set_viewer(self)  # type: ignore
                
                # Clear undo stack for new document
                undo_stack.clear()
                
                self._app_state.is_modified = False
                self._three_dot_menu.set_save_enabled(True)
            except Exception as e:
                print(f"Auto-load freenotes failed: {e}")
                self._app_state.freenotes_path = None
                self._fallback_open_pdf_setup()
        else:
            self._app_state.freenotes_path = None
            self._fallback_open_pdf_setup()

        # Track modifications via undo stack
        undo_stack.get_stack().indexChanged.connect(self._on_stack_changed)

        # Set default tool: Hand
        self._on_tool_changed("hand")
        self._toolbar.set_active_tool("hand")

        # Restore saved zoom or fit to page
        from core.app_settings import AppSettings
        saved_zoom = AppSettings.get_zoom(str(path))
        if saved_zoom is not None:
            self._page_view.set_zoom(saved_zoom)
        else:
            self._page_view.zoom_to_fit()

        # Track last opened document
        freenotes_path = path.with_suffix(".freenotes")
        if freenotes_path.exists():
            AppSettings.set_last_opened_doc(str(freenotes_path))
        else:
            AppSettings.set_last_opened_doc(str(path))
        self._update_title()

    def _fallback_open_pdf_setup(self) -> None:
        """Called when a PDF is opened and no valid .freenotes overlaid structural data exists."""
        self._sidebar.load_document(self._doc_manager, self._page_scene)
        self._sidebar.set_viewer(self)  # type: ignore
        undo_stack.clear()

    def open_freenotes(self, path: str) -> None:
        """Open a .freenotes file: load PDF first, then annotations."""
        try:
            # 1. Read the .freenotes JSON to get the PDF path
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            pdf_path = data.get("pdf_path", "")
            pdf_path = FreenotesStore.resolve_pdf_path(pdf_path, path)

            # 2. Load the PDF first (this clears the scene)
            if pdf_path and os.path.exists(pdf_path):
                self.open_pdf(Path(pdf_path), auto_load_freenotes=False)

            # 3. Now load annotations on top of the rendered pages
            _, structural_modified = FreenotesStore.load(
                path=path, scene=self._page_scene, doc_manager=self._doc_manager)

            if structural_modified:
                self._app_state.total_pages = self._doc_manager.get_page_count()
                self._sidebar.load_document(self._doc_manager, self._page_scene)
                self._sidebar.set_viewer(self)  # type: ignore

            self._app_state.freenotes_path = path
            self._app_state.is_modified = False
            self._three_dot_menu.set_save_enabled(True)
            undo_stack.clear()
            self._update_title()

            # Track last opened document
            from core.app_settings import AppSettings
            AppSettings.set_last_opened_doc(path)
        except Exception as e:
            QMessageBox.critical(self, "Fehler beim Laden", str(e))  # type: ignore

    def _on_load(self) -> None:
        """Slot for Load action from ThreeDotMenu."""
        path, _ = QFileDialog.getOpenFileName(
            self, "FreeNotes öffnen", "",  # type: ignore
            "FreeNotes (*.freenotes)",
        )
        if not path:
            return
        self.open_freenotes(path)

    def _on_save(self) -> None:
        """Slot for Save action from ThreeDotMenu."""
        path = self._app_state.freenotes_path
        if path is None:
            if self._app_state.current_pdf_path:
                pdf_path = Path(self._app_state.current_pdf_path)
                path = str(pdf_path.with_suffix(".freenotes"))
            else:
                self._on_save_as()
                return
        self._save_to(path)

    def _on_save_as(self) -> None:
        """Slot for Save As action from ThreeDotMenu."""
        default_name = ""
        if self._app_state.current_pdf_path:
            default_name = os.path.splitext(
                os.path.basename(str(self._app_state.current_pdf_path))
            )[0] + ".freenotes"
        path, _ = QFileDialog.getSaveFileName(
            self, "Speichern unter", default_name,  # type: ignore
            "FreeNotes (*.freenotes)",
        )
        if not path:
            return
        if not path.endswith(".freenotes"):
            path += ".freenotes"
        self._save_to(path)

    def _save_to(self, path: str) -> None:
        """Execute the save operation."""
        try:
            pdf_path = str(self._app_state.current_pdf_path or "")
            FreenotesStore.save(
                path=path,
                scene=self._page_scene,
                pdf_path=pdf_path,
                doc_manager=self._doc_manager,
            )
            self._app_state.freenotes_path = path
            self._app_state.is_modified = False
            self._three_dot_menu.set_save_enabled(True)
            self._update_title()
        except Exception as e:
            QMessageBox.critical(self, "Fehler beim Speichern", str(e))  # type: ignore

    def _on_export(self) -> None:
        """Slot for Export action from ThreeDotMenu."""
        pdf_path = self._app_state.current_pdf_path
        if not pdf_path:
            QMessageBox.warning(self, "Kein PDF", "Kein PDF geöffnet.")  # type: ignore
            return
        base, ext = os.path.splitext(str(pdf_path))
        default_target = f"{base}_annotiert{ext}"
        self._run_export(str(pdf_path), default_target)

    def _on_export_as(self) -> None:
        """Slot for Export As action from ThreeDotMenu."""
        pdf_path = self._app_state.current_pdf_path
        if not pdf_path:
            QMessageBox.warning(self, "Kein PDF", "Kein PDF geöffnet.")  # type: ignore
            return
        default_name = os.path.splitext(str(pdf_path))[0] + ".pdf"
        target, _ = QFileDialog.getSaveFileName(
            self, "PDF exportieren als", default_name, "PDF (*.pdf)",  # type: ignore
        )
        if not target:
            return
        self._run_export(str(pdf_path), target)

    def _run_export(self, source: str, target: str) -> None:
        """Execute the export operation with a progress dialog."""
        progress = QProgressDialog(
            "PDF wird exportiert …", "Abbrechen", 0, 100, self,  # type: ignore
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)
        progress.show()

        def on_progress(pct: int) -> None:
            progress.setValue(pct)
            QApplication.processEvents()

        try:
            exporter = PdfExporter(self._page_scene, self._doc_manager)
            exporter.export(
                source_pdf=source,
                target_pdf=target,
                progress_callback=on_progress,
            )
            progress.close()
            QMessageBox.information(
                self, "Export erfolgreich",  # type: ignore
                f"PDF gespeichert:\n{target}",
            )
        except Exception as e:
            progress.close()
            QMessageBox.critical(
                self, "Export fehlgeschlagen", str(e),  # type: ignore
            )

    def _update_title(self) -> None:
        """Update the header title based on current state."""
        pdf = str(self._app_state.current_pdf_path or "")
        if pdf:
            name = os.path.splitext(os.path.basename(pdf))[0]
            ext = os.path.splitext(pdf)[1]
        else:
            name = "FreeNotes"
            ext = ""
        mod = " •" if self._app_state.is_modified else ""
        self._title_label.setText(f"{name}{mod}")
        self._ext_label.setText(ext)

    def _on_stack_changed(self, _idx: int) -> None:
        """Mark document as modified when undo stack changes."""
        self._app_state.is_modified = True
        self._update_title()

    def _save_current_zoom(self) -> None:
        """Persist current zoom level for the active document."""
        from core.app_settings import AppSettings
        pdf = self._app_state.current_pdf_path
        zoom = self._app_state.zoom_factor
        if pdf and zoom:
            AppSettings.set_zoom(str(pdf), zoom)
