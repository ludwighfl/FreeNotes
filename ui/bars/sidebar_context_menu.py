"""Mixin providing context menu and copy/paste functionality for the SidebarWidget."""

from __future__ import annotations

from PySide6.QtGui import QContextMenuEvent, QAction
from PySide6.QtWidgets import QMenu, QWidget

# TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ui.bars.sidebar_widget import SidebarWidget


class SidebarContextMenuMixin:
    """Handles the right-click menu operations on thumbnail cards."""

    def contextMenuEvent(self: 'SidebarWidget', event: QContextMenuEvent) -> None:
        """Show page context menu on right-click."""
        if not self._cards or self._viewer is None:
            return

        # Find which card was clicked
        pos_in_container = self._container.mapFrom(
            self.viewport(),
            self.viewport().mapFrom(self, event.pos()),
        )
        clicked_idx = -1
        for i, card in enumerate(self._cards):
            if card.geometry().contains(pos_in_container):
                clicked_idx = i
                break
        if clicked_idx < 0:
            return

        from ui.components.icon_factory import IconFactory

        menu = QMenu(self)
        menu.setObjectName("pageContextMenu")

        icon_color = "#cccccc"

        act_add = QAction(
            IconFactory.create("file_plus", color=icon_color, size=16),
            "Leere Seite einfügen", self,
        )
        act_duplicate = QAction(
            IconFactory.create("copy_plus", color=icon_color, size=16),
            "Seite duplizieren", self,
        )
        act_copy = QAction(
            IconFactory.create("copy", color=icon_color, size=16),
            "Seite kopieren", self,
        )
        act_paste = QAction(
            IconFactory.create("clipboard", color=icon_color, size=16),
            "Seite einfügen", self,
        )
        act_paste.setEnabled(self._app_state.page_clipboard is not None)
        act_delete = QAction(
            IconFactory.create("trash", color="#cc4444", size=16),
            "Seite löschen", self,
        )
        act_delete.setEnabled(len(self._cards) > 1)

        menu.addAction(act_add)
        menu.addAction(act_duplicate)
        menu.addSeparator()
        menu.addAction(act_copy)
        menu.addAction(act_paste)
        menu.addSeparator()
        menu.addAction(act_delete)

        viewer = self._viewer
        idx = clicked_idx
        act_add.triggered.connect(
            lambda: viewer.add_page(idx, "after"))
        act_duplicate.triggered.connect(
            lambda: viewer.duplicate_page(idx))
        act_copy.triggered.connect(
            lambda: self._copy_page(idx))
        act_paste.triggered.connect(
            lambda: self._paste_page(idx))
        act_delete.triggered.connect(
            lambda: viewer.delete_page(idx))

        # Show dimming overlay on the viewer window
        overlay = self._show_dim_overlay()
        menu.exec(event.globalPos())
        if overlay is not None:
            overlay.close()
            overlay.deleteLater()

    # ------------------------------------------------------------------
    # Dimming overlay
    # ------------------------------------------------------------------

    def _show_dim_overlay(self: 'SidebarWidget') -> QWidget | None:
        """Create a semi-transparent overlay over the ViewerWindow to dim it
        while the sidebar context menu is visible."""
        if self._viewer is None:
            return None

        overlay = QWidget(self._viewer)
        overlay.setObjectName("sidebarDimOverlay")
        overlay.setGeometry(self._viewer.rect())
        overlay.setStyleSheet(
            "QWidget#sidebarDimOverlay { background: rgba(0, 0, 0, 100); }"
        )
        overlay.show()
        overlay.raise_()
        return overlay

    # ------------------------------------------------------------------
    # Page copy / paste
    # ------------------------------------------------------------------

    def _copy_page(self: 'SidebarWidget', page_idx: int) -> None:
        """Copy page PDF bytes + serialized annotations to AppState clipboard."""
        if self._doc_manager is None or self._scene is None:
            return

        from core.freenotes_store import FreenotesStore

        pdf_bytes = self._doc_manager.save_page_bytes(page_idx)
        annotations = FreenotesStore.serialize_page_annotations(
            self._scene, page_idx)

        # Store source page rect for position offset calculation on paste
        source_rect = self._scene.get_page_rect(page_idx)
        self._app_state.page_clipboard = {
            "pdf_bytes": pdf_bytes,
            "annotations": annotations,
            "source_rect": (source_rect.x(), source_rect.y(),
                            source_rect.width(), source_rect.height())
                           if source_rect else None,
        }

    def _paste_page(self: 'SidebarWidget', after_idx: int) -> None:
        """Insert a copied page after *after_idx*."""
        clipboard = self._app_state.page_clipboard
        if clipboard is None or self._viewer is None:
            return
        if self._doc_manager is None or self._scene is None:
            return

        from commands.add_page_command import AddPageCommand
        from core import undo_stack

        insert_at = after_idx + 1
        cmd = AddPageCommand(
            insert_at=insert_at,
            source_page_idx=None,
            scene=self._scene,
            doc_manager=self._doc_manager,
            sidebar=self,
            label="Seite einfügen",
            source_page_data=clipboard,
        )
        undo_stack.push(cmd)
