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
    
    Temporarily closes the document so the OS doesn't throw a PermissionError,
    renames the files, and reopens the document securely.
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
            "folder": path.parent
        }

    def undo(self) -> None:
        if not self._success:
            return  # only undo if redo worked
            
        app_state = AppState()
        lm = app_state.library_manager
        if lm is None:
            return
            
        try:
            current_path = app_state.current_pdf_path
            if current_path is None:
                return
                
            doc_dict = self._build_doc_dict(current_path)
            
            # Save state
            page = app_state.current_page
            
            # Close document to unlock file handlers
            self._viewer._doc_manager.close_document()
            
            new_doc = lm.rename_document(doc_dict, self._old_name)
            
            # Reopen
            if new_doc and new_doc.get("pdf"):
                self._viewer._fallback_open_pdf_setup(new_doc["pdf"])
            else:
                self._viewer._fallback_open_pdf_setup(current_path)
                
            # Restore state
            app_state.current_page = page
            # Set the label manually because title setup might have used stem
            self._viewer._title_label.setText(self._old_name)
            
            app_state.document_renamed.emit()
        except Exception as e:
            logging.error(f"Failed to undo rename document: {e}")
            traceback.print_exc()

    def redo(self) -> None:
        app_state = AppState()
        lm = app_state.library_manager
        if lm is None:
            return
            
        try:
            current_path = app_state.current_pdf_path
            if current_path is None:
                return
                
            doc_dict = self._build_doc_dict(current_path)
            
            # Save state
            page = app_state.current_page
            
            # Close document to unlock file handlers
            self._viewer._doc_manager.close_document()
            
            new_doc = lm.rename_document(doc_dict, self._new_name)
            
            # Reopen
            if new_doc and new_doc.get("pdf"):
                self._success = True
                self._viewer._fallback_open_pdf_setup(new_doc["pdf"])
                app_state.current_page = page
                self._viewer._title_label.setText(self._new_name)
                app_state.document_renamed.emit()
            else:
                self._viewer._fallback_open_pdf_setup(current_path)
                app_state.current_page = page
                
        except Exception as e:
            logging.error(f"Failed to rename document: {e}")
            traceback.print_exc()
