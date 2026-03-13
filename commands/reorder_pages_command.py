"""Undo command for reordering PDF pages via drag & drop."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from core.document_manager import DocumentManager
    from ui.page_scene import PageScene
    from ui.sidebar_widget import SidebarWidget


class ReorderPagesCommand(QUndoCommand):
    """Reorder PDF pages and their annotations.

    Stores old_order and new_order as lists of original page indices.
    """

    def __init__(
        self,
        old_order: list[int],
        new_order: list[int],
        scene: PageScene,
        doc_manager: DocumentManager,
        sidebar: SidebarWidget,
    ) -> None:
        super().__init__("Seiten neu anordnen")
        self._old_order = list(old_order)
        self._new_order = list(new_order)
        self._scene_ref = weakref.ref(scene)
        self._doc_manager_ref = weakref.ref(doc_manager)
        self._sidebar_ref = weakref.ref(sidebar)
        self._first_redo = True

    def undo(self) -> None:
        self._apply_order(self._old_order)

    def redo(self) -> None:
        if self._first_redo:
            self._first_redo = False
            return
        self._apply_order(self._new_order)

    def _apply_order(self, order: list[int]) -> None:
        scene = self._scene_ref()
        doc_manager = self._doc_manager_ref()
        sidebar = self._sidebar_ref()
        if None in (scene, doc_manager, sidebar):
            return

        # 1. Remap annotation dicts (before rebuilding scene)
        scene.reorder_annotations(order)

        # 2. Reorder PDF pages in memory
        doc_manager.reorder_pages(order)

        # 3. Rebuild scene visuals (pixmaps + item positions)
        scene.rebuild_after_reorder(doc_manager)

        # 4. Update sidebar
        sidebar.refresh_order(order)
