"""Undo command for adding a page (blank or duplicate)."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from core.document_manager import DocumentManager
    from ui.page_scene import PageScene
    from ui.sidebar_widget import SidebarWidget


class AddPageCommand(QUndoCommand):
    """Insert a blank or duplicated page at a given index."""

    def __init__(
        self,
        insert_at: int,
        source_page_idx: int | None,
        scene: PageScene,
        doc_manager: DocumentManager,
        sidebar: SidebarWidget,
        label: str = "Seite hinzufügen",
    ) -> None:
        super().__init__(label)
        self._insert_at = insert_at
        self._source_page_idx = source_page_idx
        self._scene_ref = weakref.ref(scene)
        self._doc_manager_ref = weakref.ref(doc_manager)
        self._sidebar_ref = weakref.ref(sidebar)
        self._first_redo = True
        self._saved_annotations: dict | None = None

    def undo(self) -> None:
        scene = self._scene_ref()
        doc_mgr = self._doc_manager_ref()
        sidebar = self._sidebar_ref()
        if None in (scene, doc_mgr, sidebar):
            return

        # Save annotations before removing (for re-redo)
        self._saved_annotations = scene.save_page_annotations(
            self._insert_at)

        scene.remove_page(self._insert_at, doc_mgr)
        doc_mgr.remove_page(self._insert_at)
        scene.rebuild_after_reorder(doc_mgr)
        sidebar.rebuild_all(doc_mgr)

    def redo(self) -> None:
        scene = self._scene_ref()
        doc_mgr = self._doc_manager_ref()
        sidebar = self._sidebar_ref()
        if None in (scene, doc_mgr, sidebar):
            return

        if self._first_redo:
            self._first_redo = False
            # Actually insert the page
            doc_mgr.insert_page(
                self._insert_at, self._source_page_idx)
            scene.insert_page(self._insert_at, doc_mgr)

            # Clone annotations if duplicating
            if self._source_page_idx is not None:
                scene.clone_page_annotations(
                    self._source_page_idx, self._insert_at)

            scene.rebuild_after_reorder(doc_mgr)
            sidebar.rebuild_all(doc_mgr)
            return

        # Subsequent redos
        doc_mgr.insert_page(
            self._insert_at, self._source_page_idx)
        scene.insert_page(self._insert_at, doc_mgr)
        if self._saved_annotations:
            scene.restore_page_annotations(
                self._insert_at, self._saved_annotations)
        scene.rebuild_after_reorder(doc_mgr)
        sidebar.rebuild_all(doc_mgr)
