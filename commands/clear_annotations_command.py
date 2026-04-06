"""Undo command for clearing all annotations on all pages."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING
from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene
    from core.document_manager import DocumentManager
    from ui.bars.sidebar_widget import SidebarWidget

class ClearAnnotationsCommand(QUndoCommand):
    """Delete all annotations across all pages with undo support."""

    def __init__(
        self,
        scene: PageScene,
        doc_manager: DocumentManager,
        sidebar: SidebarWidget,
        label: str = "Alle Annotationen löschen",
    ) -> None:
        super().__init__(label)
        self._scene_ref = weakref.ref(scene)
        self._doc_manager_ref = weakref.ref(doc_manager)
        self._sidebar_ref = weakref.ref(sidebar)
        self._first_redo = True
        self._saved_state: dict[int, dict] | None = None

    def undo(self) -> None:
        scene = self._scene_ref()
        if scene is None or self._saved_state is None:
            return

        for page_idx, annots in self._saved_state.items():
            scene.restore_page_annotations(page_idx, annots)
            
        doc_mgr = self._doc_manager_ref()
        if doc_mgr:
            scene.rebuild_after_reorder(doc_mgr)
            
        sidebar = self._sidebar_ref()
        if sidebar and doc_mgr:
            sidebar.rebuild_all(doc_mgr)

    def redo(self) -> None:
        scene = self._scene_ref()
        doc_mgr = self._doc_manager_ref()
        sidebar = self._sidebar_ref()
        if None in (scene, doc_mgr, sidebar):
            return

        per_page_dict = {}
        page_count = doc_mgr.get_page_count()
        for i in range(page_count):
            per_page_dict[i] = scene.save_page_annotations(i)
        self._saved_state = per_page_dict

        scene.clear_all_annotations()
