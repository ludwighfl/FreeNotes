"""Viewer file I/O mixin – handles loading, saving, and exporting documents."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog, QApplication

from core import undo_stack
from core.freenotes_store import FreenotesStore
from core.freenotes_store import FreenotesStore
from core.pdf_exporter import PdfExporter
from core.i18n import tr

if TYPE_CHECKING:
    from app.app_state import AppState
    from core.document_manager import DocumentManager
    from ui.scene.page_scene import PageScene
    from ui.bars.sidebar_widget import SidebarWidget
    from ui.popups.three_dot_menu import ThreeDotMenu
    from PySide6.QtWidgets import QLabel, QLineEdit


from PySide6.QtCore import QThread, Signal

class DocumentLoadWorker(QThread):
    """Background worker to load a PDF document without blocking the UI thread."""
    finished_loading = Signal(bool)

    def __init__(self, doc_manager: DocumentManager, path: Path):
        super().__init__()
        self.doc_manager = doc_manager
        self.path = path

    def run(self):
        success = self.doc_manager.open_document(self.path)
        self.finished_loading.emit(success)


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

    def open_pdf(self, path: Path, auto_load_freenotes: bool = True, _freenotes_to_load: str | None = None) -> None:
        """Open a PDF file in the viewer asynchronously."""
        self.clear_ui()
        self._title_label.setText(tr("viewer.loading_doc"))
        self._ext_label.setText("")
        self._breadcrumb_label.setText("")

        # Keep a reference to the worker to prevent garbage collection
        self._load_worker = DocumentLoadWorker(self._doc_manager, path)
        self._load_worker.finished_loading.connect(
            lambda success: self._on_pdf_loaded(success, path, auto_load_freenotes, _freenotes_to_load)
        )
        self._load_worker.start()

    def _on_pdf_loaded(self, success: bool, path: Path, auto_load_freenotes: bool, _freenotes_to_load: str | None) -> None:
        from PySide6.QtGui import QIntValidator

        if not success:
            QMessageBox.critical(self, tr("viewer.error_title"), tr("viewer.error_open_pdf"))  # type: ignore
            self._title_label.setText(tr("viewer.load_error"))
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
        
        # Safely deactivate any active tool before destroying C++ objects
        self._page_scene.set_tool(None)
        
        self._page_scene.load_document(self._doc_manager)

        if _freenotes_to_load:
            self._load_specific_freenotes(_freenotes_to_load)
        else:
            # Check if corresponding .freenotes exists and load it automatically
            freenotes_path = path.with_suffix(".freenotes")
            if auto_load_freenotes:
                if not freenotes_path.exists():
                    try:
                        # Create empty .freenotes file immediately
                        FreenotesStore.save(
                            path=str(freenotes_path),
                            scene=self._page_scene,
                            pdf_path=str(path),
                            doc_manager=self._doc_manager,
                        )
                    except Exception as e:
                        print(f"Failed to create empty freenotes file: {e}")

                if freenotes_path.exists():
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
                    except Exception as e:
                        print(f"Auto-load freenotes failed: {e}")
                        self._app_state.freenotes_path = None
                        self._fallback_open_pdf_setup()
                else:
                    self._app_state.freenotes_path = None
                    self._fallback_open_pdf_setup()
            else:
                self._app_state.freenotes_path = None
                self._fallback_open_pdf_setup()

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

            # 2. Load the PDF first (this clears the scene) asynchronously
            if pdf_path and os.path.exists(pdf_path):
                self.open_pdf(Path(pdf_path), auto_load_freenotes=False, _freenotes_to_load=path)
            else:
                QMessageBox.critical(self, tr("viewer.error_title"), tr("viewer.error_missing_pdf"))  # type: ignore

        except Exception as e:
            QMessageBox.critical(self, tr("viewer.load_error"), str(e))  # type: ignore

    def _load_specific_freenotes(self, path: str) -> None:
        """Called internally after the PDF is loaded to load the corresponding .freenotes data."""
        try:
            from PySide6.QtGui import QIntValidator
            
            _, structural_modified = FreenotesStore.load(
                path=path, scene=self._page_scene, doc_manager=self._doc_manager)

            if structural_modified:
                self._app_state.total_pages = self._doc_manager.get_page_count()
                self._total_pages_label.setText(str(self._app_state.total_pages))
                self._page_input.setValidator(QIntValidator(1, self._app_state.total_pages, self))

            self._sidebar.load_document(self._doc_manager, self._page_scene)
            self._sidebar.set_viewer(self)  # type: ignore

            self._app_state.freenotes_path = path
            undo_stack.clear()
            self._update_title()

            # Track last opened document
            from core.app_settings import AppSettings
            AppSettings.set_last_opened_doc(path)
        except Exception as e:
            QMessageBox.critical(self, tr("viewer.load_error"), str(e))  # type: ignore

    def _on_load(self) -> None:
        """Slot for Load action from ThreeDotMenu."""
        path, _ = QFileDialog.getOpenFileName(
            self, tr("viewer.open_freenotes"), "",  # type: ignore
            "FreeNotes (*.freenotes)",
        )
        if not path:
            return
        self.open_freenotes(path)

    def save_document(self) -> None:
        """Execute the autosave operation."""
        path = self._app_state.freenotes_path
        if not path:
            return
        
        try:
            pdf_path = str(self._app_state.current_pdf_path or "")
            doc_mgr = self._doc_manager
            
            if doc_mgr and getattr(doc_mgr, 'is_structurally_modified', False):
                # Structural changes occurred. We must save them to the physical PDF.
                # Stop caching and free locks.
                if hasattr(self, '_page_scene') and hasattr(self._page_scene, '_tile_renderer'):
                    renderer = self._page_scene._tile_renderer
                    renderer.cancel_all()
                    renderer.wait_for_idle()
                
                doc_mgr.overwrite_pdf()
                
                # Invalidate cache, so that next tile requests trigger new pool connections
                if hasattr(self, '_page_scene') and hasattr(self._page_scene, '_tile_cache'):
                    self._page_scene._tile_cache.invalidate_all()
            
            FreenotesStore.save(
                path=path,
                scene=self._page_scene,
                pdf_path=pdf_path,
                doc_manager=self._doc_manager,
            )
            # Autosave complete. No feedback required.
        except Exception as e:
            print(f"Autosave failed: {e}")

    def _on_clear_annotations(self) -> None:
        """Slot for Clear Annotations action from ThreeDotMenu."""
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.warning(
            self,  # type: ignore
            tr("viewer.clear_annotations"),
            tr("viewer.clear_annotations_msg"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            from commands.clear_annotations_command import ClearAnnotationsCommand
            cmd = ClearAnnotationsCommand(
                scene=self._page_scene,
                doc_manager=self._doc_manager,
                sidebar=self._sidebar
            )
            undo_stack.push(cmd)

    def _on_export(self) -> None:
        """Slot for Export action from ThreeDotMenu."""
        pdf_path = self._app_state.current_pdf_path
        if not pdf_path:
            QMessageBox.warning(self, tr("viewer.no_pdf_title"), tr("viewer.no_pdf_msg"))  # type: ignore
            return
        base, ext = os.path.splitext(str(pdf_path))
        default_target = f"{base}_annotiert{ext}"
        self._run_export(str(pdf_path), default_target)

    def _on_export_as(self) -> None:
        """Slot for Export As action from ThreeDotMenu."""
        pdf_path = self._app_state.current_pdf_path
        if not pdf_path:
            QMessageBox.warning(self, tr("viewer.no_pdf_title"), tr("viewer.no_pdf_msg"))  # type: ignore
            return
        default_name = os.path.splitext(str(pdf_path))[0] + ".pdf"
        target, _ = QFileDialog.getSaveFileName(
            self, tr("viewer.export_pdf_as"), default_name, "PDF (*.pdf)",  # type: ignore
        )
        if not target:
            return
        self._run_export(str(pdf_path), target)

    def _run_export(self, source: str, target: str) -> None:
        """Execute the export operation with a progress dialog."""
        progress = QProgressDialog(
            tr("viewer.export_progress"), tr("settings.library.cancel"), 0, 100, self,  # type: ignore
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
                self, tr("settings.library.export_success"),  # type: ignore
                tr("settings.library.pdf_saved").format(target),
            )
        except Exception as e:
            progress.close()
            QMessageBox.critical(
                self, tr("settings.library.export_failed"), str(e),  # type: ignore
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
        self._title_label.setText(name)
        self._ext_label.setText(ext)

    def _on_stack_changed(self, _idx: int) -> None:
        """Start autosave timer when undo stack changes."""
        if hasattr(self, '_autosave_timer'):
            self._autosave_timer.start(1000)

    def _save_current_zoom(self) -> None:
        """Persist current zoom level for the active document."""
        from core.app_settings import AppSettings
        pdf = self._app_state.current_pdf_path
        zoom = self._app_state.zoom_factor
        if pdf and zoom:
            AppSettings.set_zoom(str(pdf), zoom)
