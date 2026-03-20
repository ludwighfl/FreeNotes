"""Mixin for handling page reordering, insertion, deletion and cloning."""

from __future__ import annotations
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtWidgets import QGraphicsPixmapItem
from typing import TYPE_CHECKING
from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem
from items.text_box_item import TextBoxItem
from items.shape_item import ShapeItem

if TYPE_CHECKING:
    from ui.page_scene import PageScene
    from core.document_manager import DocumentManager


class ScenePageManagerMixin:
    """Mixin for managing pages in the PageScene.

    Expects the host class to provide:
        _stroke_items: dict
        _highlight_items: dict
        _text_box_items: dict
        _shape_items: dict
        _page_items: list
        _page_rects: list
        PAGE_GAP: int
        removeItem(): method
        addItem(): method
    """

    def reorder_annotations(self, new_order: list[int]) -> None:
        """Remap annotation dicts according to new_order.

        new_order[new_pos] = old_page_index.
        Must be called BEFORE doc_manager.reorder_pages().
        """
        def remap(d: dict) -> dict:
            new_d: dict = {}
            for new_pos, old_idx in enumerate(new_order):
                if old_idx in d:
                    items = d[old_idx]
                    new_d[new_pos] = items
                    for item in items:
                        if hasattr(item, '_page_index'):
                            item._page_index = new_pos
            return new_d

        self._stroke_items = remap(self._stroke_items)
        self._highlight_items = remap(self._highlight_items)
        self._text_box_items = remap(self._text_box_items)
        self._shape_items = remap(self._shape_items)

    def rebuild_after_reorder(self, doc_manager: DocumentManager) -> None:
        """Rebuild page pixmaps and reposition annotations after reorder.

        Must be called AFTER doc_manager.reorder_pages().
        """
        page_count = doc_manager.get_page_count()
        if page_count == 0:
            return

        # Collect all annotation items and temporarily remove from scene
        all_annotations: dict[int, list] = {}
        for idx in range(page_count):
            items = []
            for d in (self._stroke_items, self._highlight_items,
                      self._text_box_items, self._shape_items):
                items.extend(d.get(idx, []))
            all_annotations[idx] = items

        # Store old page rects for offset calculation
        old_page_rects = list(self._page_rects)

        # Remove old page pixmap items
        for pix_item in self._page_items:
            self.removeItem(pix_item)
        self._page_items.clear()
        self._page_rects.clear()

        # Re-render pages in new order
        y_offset: float = self.PAGE_GAP
        for i in range(page_count):
            pixmap = doc_manager.get_page_pixmap(i)
            item = QGraphicsPixmapItem(pixmap)
            item.setTransformationMode(
                Qt.TransformationMode.SmoothTransformation)

            dpr = pixmap.devicePixelRatio()
            logical_w = pixmap.width() / dpr
            logical_h = pixmap.height() / dpr

            item.setPos(0, y_offset)
            self._page_items.append(item)
            self.addItem(item)

            page_rect = QRectF(0, y_offset, logical_w, logical_h)
            self._page_rects.append(page_rect)
            y_offset += logical_h + self.PAGE_GAP

        # Center horizontally
        if self._page_items:
            max_width = max(
                it.pixmap().width() / it.pixmap().devicePixelRatio()
                for it in self._page_items
            )
            for i, it in enumerate(self._page_items):
                pix = it.pixmap()
                lw = pix.width() / pix.devicePixelRatio()
                lh = pix.height() / pix.devicePixelRatio()
                x_off = (max_width - lw) / 2.0
                it.setPos(x_off, it.pos().y())
                self._page_rects[i] = QRectF(
                    x_off, it.pos().y(), lw, lh)

        # Reposition annotation items to new page y-offsets
        for idx in range(page_count):
            if idx >= len(self._page_rects):
                break
            new_rect = self._page_rects[idx]
            # Get old rect for this page's annotations (use old_page_rects if available)
            for item in all_annotations.get(idx, []):
                old_pos = item.pos()
                # Find which old page this item was on based on its old _page_index
                old_page_idx = idx  # annotations already remapped
                if old_page_idx < len(old_page_rects):
                    old_rect = old_page_rects[old_page_idx]
                    # Compute relative position within old page
                    rel_x = old_pos.x() - old_rect.x()
                    rel_y = old_pos.y() - old_rect.y()
                    # Apply to new page position
                    item.setPos(QPointF(
                        new_rect.x() + rel_x,
                        new_rect.y() + rel_y,
                    ))

    def insert_page(self, at_index: int, doc_manager: DocumentManager) -> None:
        """Insert an empty annotation slot at at_index.

        Shifts all annotation indices >= at_index up by 1.
        """
        for d in (self._stroke_items, self._highlight_items,
                  self._text_box_items, self._shape_items):
            new_d: dict = {}
            for idx, items in d.items():
                new_idx = idx + 1 if idx >= at_index else idx
                for item in items:
                    if hasattr(item, '_page_index') and item._page_index >= at_index:
                        item._page_index += 1
                new_d[new_idx] = items
            d.clear()
            d.update(new_d)

    def remove_page(self, page_idx: int, doc_manager: DocumentManager) -> None:
        """Remove all annotations on page_idx and shift indices down."""
        for d in (self._stroke_items, self._highlight_items,
                  self._text_box_items, self._shape_items):
            # Remove items on the deleted page from scene
            for item in d.get(page_idx, []):
                self.removeItem(item)
            # Re-index
            new_d: dict = {}
            for idx, items in d.items():
                if idx == page_idx:
                    continue
                new_idx = idx - 1 if idx > page_idx else idx
                for item in items:
                    if hasattr(item, '_page_index') and item._page_index > page_idx:
                        item._page_index -= 1
                new_d[new_idx] = items
            d.clear()
            d.update(new_d)

    def clone_page_annotations(
        self, source_idx: int, target_idx: int
    ) -> None:
        """Deep-copy annotations from source_idx to target_idx."""
        mapping = [
            (self._stroke_items, StrokeItem),
            (self._highlight_items, HighlightItem),
            (self._text_box_items, TextBoxItem),
            (self._shape_items, ShapeItem),
        ]
        for d, item_cls in mapping:
            for item in d.get(source_idx, []):
                try:
                    data = item.to_dict()
                    new_item = item_cls.from_dict(data)
                    new_item._page_index = target_idx
                    d.setdefault(target_idx, []).append(new_item)
                    self.addItem(new_item)
                except Exception:
                    pass  # skip items that can't be cloned

    def save_page_annotations(self, page_idx: int) -> dict:
        """Save annotation item references for undo (removes from scene)."""
        saved: dict = {
            "strokes": list(self._stroke_items.get(page_idx, [])),
            "highlights": list(self._highlight_items.get(page_idx, [])),
            "textboxes": list(self._text_box_items.get(page_idx, [])),
            "shapes": list(self._shape_items.get(page_idx, [])),
        }
        return saved

    def restore_page_annotations(
        self, page_idx: int, saved: dict
    ) -> None:
        """Restore previously saved annotation items to page_idx."""
        mapping = {
            "strokes": self._stroke_items,
            "highlights": self._highlight_items,
            "textboxes": self._text_box_items,
            "shapes": self._shape_items,
        }
        for key, items in saved.items():
            d = mapping[key]
            d.setdefault(page_idx, [])
            for item in items:
                item._page_index = page_idx
                if item.scene() is None:
                    self.addItem(item)
                d[page_idx].append(item)
