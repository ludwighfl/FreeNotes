"""Undo command for renaming a document."""

from __future__ import annotations

import logging
import traceback
from typing import TYPE_CHECKING
from pathlib import Path

from PySide6.QtGui import QUndoCommand

from app.app_state import AppState

if TYPE_CHECKING:
    from ui.windows.viewer_window import ViewerWindow


class RenameDocumentCommand(QUndoCommand):
    """Rename the current document and update UI.

    Closes the document so the OS doesn't throw a PermissionError,
    renames the files via LibraryManager, then reopens via open_pdf.
    """

    def __init__(
        self,
        viewer: "ViewerWindow",
        old_name: str,
        new_name: str,
        label: str = "Dokument umbenennen",
    ) -> None:
        super().__init__(label)
        self._viewer = viewer
        self._old_name = old_name
        self._new_name = new_name
        self._success = False

    def _build_doc_dict(self, path: Path) -> dict:
        fn_path = path.with_suffix(".freenotes")
        return {
            "pdf": path,
            "freenotes": fn_path if fn_path.exists() else None,
            "name": path.stem,
            "folder": path.parent,
        }

    def _rename_and_reopen(self, target_name: str) -> bool:
        """Close document, rename on disk, reopen. Returns True on success."""
        app_state = AppState()
        lm = app_state.library_manager
        if lm is None:
            return False

        current_path = app_state.current_pdf_path
        if current_path is None:
            return False

        doc_dict = self._build_doc_dict(current_path)
        page = app_state.current_page

        # Stop tile renderer to release file locks before renaming
        if hasattr(self._viewer, '_page_scene'):
            scene = self._viewer._page_scene
            if hasattr(scene, '_tile_renderer'):
                scene._tile_renderer.cancel_all()
                scene._tile_renderer.wait_for_idle()

        # Close document to unlock file handles
        self._viewer._doc_manager.close_document()

        new_doc = lm.rename_document(doc_dict, target_name)

        new_pdf = new_doc.get("pdf") if new_doc else None
        if new_pdf and new_pdf.exists():
            self._viewer.open_pdf(new_pdf)
            app_state.current_page = page
            self._viewer._title_label.setText(target_name)
            app_state.document_renamed.emit()
            return True
        else:
            # Rename failed — try to reopen original
            if current_path.exists():
                self._viewer.open_pdf(current_path)
                app_state.current_page = page
            return False

    def undo(self) -> None:
        if not self._success:
            return
        try:
            self._rename_and_reopen(self._old_name)
        except Exception as e:
            logging.error(f"Failed to undo rename: {e}")
            traceback.print_exc()

    def redo(self) -> None:
        try:
            self._success = self._rename_and_reopen(self._new_name)
        except Exception as e:
            logging.error(f"Failed to rename document: {e}")
            traceback.print_exc()
