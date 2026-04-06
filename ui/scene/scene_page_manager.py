"""Mixin for handling page reordering, insertion, deletion and cloning."""

from __future__ import annotations
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtWidgets import QGraphicsPixmapItem
from typing import TYPE_CHECKING
from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem
from items.text_box_item import TextBoxItem
from items.shape_item import ShapeItem
from items.image_item import ImageItem

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene
    from core.document_manager import DocumentManager


class ScenePageManagerMixin:
    """Mixin for managing pages in the PageScene.

    Expects the host class to provide:
        _stroke_items: dict
        _highlight_items: dict
        _text_box_items: dict
        _shape_items: dict
        _image_items: dict
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
                            item._old_page_index = item._page_index
                            item._page_index = new_pos
            return new_d

        self._stroke_items = remap(self._stroke_items)
        self._highlight_items = remap(self._highlight_items)
        self._text_box_items = remap(self._text_box_items)
        self._shape_items = remap(self._shape_items)
        self._image_items = remap(self._image_items)

    def rebuild_after_reorder(self, doc_manager: DocumentManager, order: list[int] = None) -> None:
        """Rebuild page pixmaps and reposition annotations after reorder.

        Must be called AFTER doc_manager.reorder_pages().
        If `order` is provided, it does a fast list rearrangement instead
        of destroying and recreating all scene items.
        """
        # Invalidate tile cache — PDF page content has moved
        if hasattr(self, '_tile_cache'):
            self._tile_cache.invalidate_all()
        if hasattr(self, '_tile_renderer'):
            self._tile_renderer.cancel_all()

        # Remove stale tile pixmap items from scene
        if hasattr(self, '_tile_items'):
            for tile_item in self._tile_items.values():
                self.removeItem(tile_item)
            self._tile_items.clear()
        if hasattr(self, '_pending_tiles'):
            self._pending_tiles.clear()

        page_count = doc_manager.get_page_count()
        if page_count == 0:
            return

        # Collect all annotation items
        all_annotations: dict[int, list] = {}
        for idx in range(page_count):
            items = []
            for d in (self._stroke_items, self._highlight_items,
                      self._text_box_items, self._shape_items, self._image_items):
                items.extend(d.get(idx, []))
            all_annotations[idx] = items

        # Store old page rects for offset calculation
        old_page_rects = list(self._page_rects)

        if order is not None and len(order) == len(self._page_items):
            # FAST PATH: Reorder existing items
            self._page_items = [self._page_items[i] for i in order]
            self._page_rects = [self._page_rects[i] for i in order]
            self._page_states = [self._page_states[i] for i in order]
            
            self._page_y_offsets.clear()
            self._rendered_set.clear()

            y_offset = float(self.PAGE_GAP)
            for i, rect in enumerate(self._page_rects):
                w, h = rect.width(), rect.height()
                self._page_items[i].setPos(rect.x(), y_offset)
                self._page_rects[i] = QRectF(rect.x(), y_offset, w, h)
                self._page_y_offsets.append(y_offset)
                if self._page_states[i] == "rendered":
                    self._rendered_set.add(i)
                y_offset += h + self.PAGE_GAP
        else:
            # FALLBACK PATH: Destroy and recreate
            for pix_item in self._page_items:
                self.removeItem(pix_item)
            self._page_items.clear()
            self._page_rects.clear()
            self._page_states.clear()
            self._page_y_offsets.clear()
            self._rendered_set.clear()

            scale = getattr(self, 'RENDER_DPI', 144) / 72.0
            placeholder = getattr(self, '_get_placeholder_pixmap', lambda: None)()
            if placeholder is None:
                from PySide6.QtGui import QPixmap
                placeholder = QPixmap()

            y_offset = float(self.PAGE_GAP)
            for i in range(page_count):
                w_pt, h_pt = doc_manager.get_page_size(i)
                log_w = w_pt * scale
                log_h = h_pt * scale

                item = QGraphicsPixmapItem(placeholder)
                item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
                if log_w > 0:
                    item.setScale(log_w / 2.0)
                item.setPos(0, y_offset)
                
                self._page_items.append(item)
                self.addItem(item)
                self._page_rects.append(QRectF(0, y_offset, log_w, log_h))
                self._page_states.append("placeholder")
                self._page_y_offsets.append(y_offset)
                y_offset += log_h + self.PAGE_GAP

        # Center horizontally
        if hasattr(self, '_center_pages'):
            self._center_pages()
        else:
            if self._page_items:
                max_width = max(r.width() for r in self._page_rects)
                for i, it in enumerate(self._page_items):
                    lw = self._page_rects[i].width()
                    lh = self._page_rects[i].height()
                    x_off = (max_width - lw) / 2.0
                    it.setPos(x_off, it.pos().y())
                    self._page_rects[i] = QRectF(x_off, it.pos().y(), lw, lh)

        # Reposition annotation items to new page y-offsets
        for idx in range(page_count):
            if idx >= len(self._page_rects):
                break
            new_rect = self._page_rects[idx]
            for item in all_annotations.get(idx, []):
                old_pos = item.pos()
                # Derive old index from order array if available (guaranteed correct), else fallback
                old_page_idx = order[idx] if order else getattr(item, '_old_page_index', idx)
                if old_page_idx < len(old_page_rects):
                    old_rect = old_page_rects[old_page_idx]
                    rel_x = old_pos.x() - old_rect.x()
                    rel_y = old_pos.y() - old_rect.y()
                    item.setPos(QPointF(new_rect.x() + rel_x, new_rect.y() + rel_y))
                if hasattr(item, '_old_page_index'):
                    delattr(item, '_old_page_index')
                    
        # Trigger tile rendering for newly visible pages.
        # Use QGraphicsScene.views() to reach the PageView's render timer,
        # since _viewport_rect / _on_scroll_changed live on PageView, not Scene.
        from PySide6.QtCore import QTimer
        for view in self.views():
            if hasattr(view, '_on_render_timer'):
                QTimer.singleShot(50, view._on_render_timer)

    def insert_page(self, at_index: int, doc_manager: DocumentManager) -> None:
        """Insert an empty annotation slot at at_index.

        Shifts all annotation indices >= at_index up by 1.
        """
        for d in (self._stroke_items, self._highlight_items,
                  self._text_box_items, self._shape_items, self._image_items):
            new_d: dict = {}
            for idx, items in d.items():
                new_idx = idx + 1 if idx >= at_index else idx
                for item in items:
                    if hasattr(item, '_page_index'):
                        item._old_page_index = item._page_index
                        if item._page_index >= at_index:
                            item._page_index += 1
                new_d[new_idx] = items
            d.clear()
            d.update(new_d)

        # Invalidate tile system — page indices have shifted
        if hasattr(self, '_tile_cache'):
            self._tile_cache.invalidate_all()
        if hasattr(self, '_tile_items'):
            for tile_item in self._tile_items.values():
                self.removeItem(tile_item)
            self._tile_items.clear()
        if hasattr(self, '_pending_tiles'):
            self._pending_tiles.clear()

    def clear_all_annotations(self) -> None:
        """Clear all annotation dicts and remove items from scene, leaving pages intact."""
        for d in (self._stroke_items, self._highlight_items,
                  self._text_box_items, self._shape_items, self._image_items):
            for items in d.values():
                for item in items:
                    self.removeItem(item)
            d.clear()

    def remove_page(self, page_idx: int, doc_manager: DocumentManager) -> None:
        """Remove all annotations on page_idx and shift indices down."""
        for d in (self._stroke_items, self._highlight_items,
                  self._text_box_items, self._shape_items, self._image_items):
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
                    if hasattr(item, '_page_index'):
                        item._old_page_index = item._page_index
                        if item._page_index > page_idx:
                            item._page_index -= 1
                new_d[new_idx] = items
            d.clear()
            d.update(new_d)

        # Invalidate tile system — page indices have shifted
        if hasattr(self, '_tile_cache'):
            self._tile_cache.invalidate_all()
        if hasattr(self, '_tile_items'):
            for tile_item in self._tile_items.values():
                self.removeItem(tile_item)
            self._tile_items.clear()
        if hasattr(self, '_pending_tiles'):
            self._pending_tiles.clear()

    def clone_page_annotations(
        self, source_idx: int, target_idx: int
    ) -> None:
        """Deep-copy annotations from source_idx to target_idx."""
        mapping = [
            (self._stroke_items, StrokeItem),
            (self._highlight_items, HighlightItem),
            (self._text_box_items, TextBoxItem),
            (self._shape_items, ShapeItem),
            (self._image_items, ImageItem),
        ]
        for d, item_cls in mapping:
            for item in d.get(source_idx, []):
                try:
                    data = item.to_dict()
                    new_item = item_cls.from_dict(data)
                    new_item._page_index = target_idx
                    new_item._old_page_index = source_idx  # Keep absolute tracking!
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
            "images": list(self._image_items.get(page_idx, [])),
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
            "images": self._image_items,
        }
        for key, items in saved.items():
            d = mapping[key]
            d.setdefault(page_idx, [])
            for item in items:
                item._page_index = page_idx
                if item.scene() is None:
                    self.addItem(item)
                d[page_idx].append(item)
