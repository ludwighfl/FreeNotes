"""Undo command for deleting a page."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

import fitz
from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from core.document_manager import DocumentManager
    from ui.scene.page_scene import PageScene
    from ui.bars.sidebar_widget import SidebarWidget

from app.app_state import AppState


class DeletePageCommand(QUndoCommand):
    """Delete a single page (undoable)."""

    def __init__(
        self,
        page_idx: int,
        scene: PageScene,
        doc_manager: DocumentManager,
        sidebar: SidebarWidget,
    ) -> None:
        super().__init__("Seite löschen")
        self._page_idx = page_idx
        self._scene_ref = weakref.ref(scene)
        self._doc_manager_ref = weakref.ref(doc_manager)
        self._sidebar_ref = weakref.ref(sidebar)
        self._first_redo = True
        self._saved_annotations: dict | None = None
        self._saved_pdf_bytes: bytes | None = None

    def undo(self) -> None:
        scene = self._scene_ref()
        doc_mgr = self._doc_manager_ref()
        sidebar = self._sidebar_ref()
        if None in (scene, doc_mgr, sidebar):
            return

        # Restore PDF page
        doc_mgr.restore_page(
            self._page_idx, 
            self._saved_pdf_bytes, 
            getattr(self, "_saved_map_idx", -1)
        )

        # Restore scene page + annotations
        scene.insert_page(self._page_idx, doc_mgr)
        if self._saved_annotations:
            scene.restore_page_annotations(
                self._page_idx, self._saved_annotations)
        scene.relayout_after_insert(self._page_idx, doc_mgr)
        sidebar.insert_card(self._page_idx)
        AppState().total_pages = doc_mgr.get_page_count()
        self._navigate_to(self._page_idx)

    def redo(self) -> None:
        scene = self._scene_ref()
        doc_mgr = self._doc_manager_ref()
        sidebar = self._sidebar_ref()
        if None in (scene, doc_mgr, sidebar):
            return

        if self._first_redo:
            self._first_redo = False
            # Save state before deleting
            self._saved_annotations = scene.save_page_annotations(
                self._page_idx)
            self._saved_pdf_bytes = doc_mgr.save_page_bytes(
                self._page_idx)
            self._saved_map_idx = doc_mgr.page_map[self._page_idx]

        # Remove page
        scene.remove_page(self._page_idx, doc_mgr)
        doc_mgr.remove_page(self._page_idx)
        scene.relayout_after_delete(self._page_idx, doc_mgr)
        sidebar.remove_card(self._page_idx)
        AppState().total_pages = doc_mgr.get_page_count()
        self._navigate_to(max(0, self._page_idx - 1))

    def _navigate_to(self, target_idx: int) -> None:
        """Scroll the viewer and sidebar to the target page."""
        from PySide6.QtCore import QTimer

        sidebar = self._sidebar_ref()
        if sidebar is None:
            return
        viewer = getattr(sidebar, '_viewer', None)
        if viewer is None:
            return
        page_view = getattr(viewer, '_page_view', None)
        if page_view is None:
            return

        def _do_navigate():
            AppState().current_page = target_idx
            page_view.scroll_to_page(target_idx)

        # Deferred so rebuild has fully completed
        QTimer.singleShot(60, _do_navigate)
