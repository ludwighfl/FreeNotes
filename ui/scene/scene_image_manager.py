"""Mixin to handle the insertion of external files like images into the scene."""

from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QFileDialog

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class SceneImageManagerMixin:
    """Provides methods for picking and placing image items onto the PDF canvas."""

    def insert_image_from_file_dialog(self: 'PageScene', pos: QPointF | None = None) -> None:
        """Open a file dialog to select an image, then insert it at the given pos or center."""
        
        # Use the first view to get a parent widget for the dialog
        views = self.views()
        parent_widget = views[0] if views else None

        file_path, _ = QFileDialog.getOpenFileName(
            parent_widget,
            "Bild einfügen",
            "",
            "Bilder (*.png *.jpg *.jpeg *.webp);;Alle Dateien (*.*)"
        )

        if not file_path or not os.path.exists(file_path):
            return

        from app.app_state import AppState
        page_idx = -1

        if pos is None:
            # Drop at center of current page
            page_idx = AppState().current_page
            page_rect = self.get_page_rect(page_idx)
            if not page_rect.isEmpty():
                pos = QPointF(page_rect.center().x(), page_rect.top() + 50)
            else:
                pos = QPointF(100, 100)
        else:
            page_idx = self.get_page_index_at(pos)
            if page_idx < 0:
                page_idx = AppState().current_page

        try:
            from items.image_item import ImageItem
            item = ImageItem.from_image_file(file_path, pos, page_idx)
            
            # Scale down large images
            page_rect = self.get_page_rect(page_idx)
            if not page_rect.isEmpty() and item._rect.width() > page_rect.width() * 0.8:
                scale = (page_rect.width() * 0.8) / item._rect.width()
                new_w = item._rect.width() * scale
                new_h = item._rect.height() * scale
                from PySide6.QtCore import QRectF
                item.set_rect(QRectF(pos.x(), pos.y(), new_w, new_h))
                
            self.addItem(item)
            self.add_item_to_registry(item)

            # Push undo command
            from commands.paste_items_command import PasteItemsCommand
            from core import undo_stack
            cmd = PasteItemsCommand([item], self)
            undo_stack.push(cmd)

            # Select dropped items
            self.set_selection([item])

            # Auto-switch to hand tool
            self.tool_switch_requested.emit("hand")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Image insert failed: %s", e)
