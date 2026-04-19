"""Undo command for adding a page (blank, duplicate, or pasted from clipboard)."""

from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

if TYPE_CHECKING:
    from core.document_manager import DocumentManager
    from ui.scene.page_scene import PageScene
    from ui.bars.sidebar_widget import SidebarWidget

from app.app_state import AppState


class AddPageCommand(QUndoCommand):
    """Insert a blank, duplicated, or pasted page at a given index.

    Args:
        insert_at: Target page index.
        source_page_idx: If set, duplicate this page from the current doc.
        source_page_data: If set, insert from clipboard data dict
                          {'pdf_bytes': bytes, 'annotations': dict | None}.
                          Takes precedence over *source_page_idx*.
    """

    def __init__(
        self,
        insert_at: int,
        source_page_idx: int | None,
        scene: PageScene,
        doc_manager: DocumentManager,
        sidebar: SidebarWidget,
        label: str = "Seite hinzufügen",
        source_page_data: dict | None = None,
    ) -> None:
        super().__init__(label)
        self._insert_at = insert_at
        self._source_page_idx = source_page_idx
        self._source_page_data = source_page_data
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
        AppState().total_pages = doc_mgr.get_page_count()

    def redo(self) -> None:
        scene = self._scene_ref()
        doc_mgr = self._doc_manager_ref()
        sidebar = self._sidebar_ref()
        if None in (scene, doc_mgr, sidebar):
            return

        if self._first_redo:
            self._first_redo = False

            if self._source_page_data is not None:
                # Insert from clipboard bytes
                pdf_bytes = self._source_page_data.get("pdf_bytes", b"")
                doc_mgr.insert_page(self._insert_at, source_bytes=pdf_bytes)
                scene.insert_page(self._insert_at, doc_mgr)

                # Rebuild FIRST so the target page rect exists
                scene.rebuild_after_reorder(doc_mgr)
                sidebar.rebuild_all(doc_mgr)
                AppState().total_pages = doc_mgr.get_page_count()

                # Now restore annotations (target page rect is available)
                annotations = self._source_page_data.get("annotations")
                if annotations:
                    from core.freenotes_store import FreenotesStore

                    # Compute position offset: source rect → target rect
                    pos_offset = None
                    source_rect = self._source_page_data.get("source_rect")
                    target_rect = scene.get_page_rect(self._insert_at)
                    if source_rect and target_rect and not target_rect.isEmpty():
                        sx, sy = source_rect[0], source_rect[1]
                        tx, ty = target_rect.x(), target_rect.y()
                        pos_offset = (tx - sx, ty - sy)

                    FreenotesStore.deserialize_page_annotations(
                        scene, self._insert_at, annotations,
                        pos_offset=pos_offset)
            else:
                # Blank or duplicate insert
                doc_mgr.insert_page(
                    self._insert_at, self._source_page_idx)
                scene.insert_page(self._insert_at, doc_mgr)

                # Clone annotations if duplicating
                if self._source_page_idx is not None:
                    scene.clone_page_annotations(
                        self._source_page_idx, self._insert_at)

                scene.rebuild_after_reorder(doc_mgr)
                sidebar.rebuild_all(doc_mgr)
                AppState().total_pages = doc_mgr.get_page_count()
            self._navigate_to_page()
            return

        # Subsequent redos — always use saved annotations
        if self._source_page_data is not None:
            pdf_bytes = self._source_page_data.get("pdf_bytes", b"")
            doc_mgr.insert_page(self._insert_at, source_bytes=pdf_bytes)
        else:
            doc_mgr.insert_page(
                self._insert_at, self._source_page_idx)
        scene.insert_page(self._insert_at, doc_mgr)
        if self._saved_annotations:
            scene.restore_page_annotations(
                self._insert_at, self._saved_annotations)
        scene.rebuild_after_reorder(doc_mgr)
        sidebar.rebuild_all(doc_mgr)
        AppState().total_pages = doc_mgr.get_page_count()
        self._navigate_to_page()

    def _navigate_to_page(self) -> None:
        """Scroll the viewer and sidebar to the newly inserted page."""
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
        idx = self._insert_at

        def _do_navigate():
            AppState().current_page = idx
            page_view.scroll_to_page(idx)

        # Deferred so rebuild has fully completed
        QTimer.singleShot(60, _do_navigate)
