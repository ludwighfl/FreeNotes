"""Scene registry mixin – per-page tracking of annotation items."""

from __future__ import annotations

from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem
from items.text_box_item import TextBoxItem
from items.shape_item import ShapeItem
from items.image_item import ImageItem


class SceneRegistryMixin:
    """Mixin providing per-page item registries for PageScene.

    Expects the host class to provide:
        _stroke_items: dict[int, list[StrokeItem]]
        _highlight_items: dict[int, list[HighlightItem]]
        _text_box_items: dict[int, list[TextBoxItem]]
        _shape_items: dict[int, list[ShapeItem]]
        _image_items: dict[int, list[ImageItem]]
        removeItem(): method (from QGraphicsScene)
        update(): method
    """

    # ------------------------------------------------------------------
    # Stroke tracking
    # ------------------------------------------------------------------

    def add_stroke_item(self, item: StrokeItem, page_index: int) -> None:
        """Track a stroke item by its page index.

        Args:
            item: The StrokeItem to track.
            page_index: The page this stroke belongs to.
        """
        if page_index not in self._stroke_items:
            self._stroke_items[page_index] = []
        self._stroke_items[page_index].append(item)

    def get_strokes_for_page(self, page_index: int) -> list[StrokeItem]:
        """Return all stroke items on a given page.

        Args:
            page_index: Zero-based page index.

        Returns:
            List of StrokeItem objects, or empty list.
        """
        return self._stroke_items.get(page_index, [])

    # ------------------------------------------------------------------
    # Highlight tracking
    # ------------------------------------------------------------------

    def add_highlight_item(self, item: HighlightItem, page_index: int) -> None:
        """Track a highlight item by its page index."""
        if page_index not in self._highlight_items:
            self._highlight_items[page_index] = []
        self._highlight_items[page_index].append(item)

    def get_highlights_for_page(self, page_index: int) -> list[HighlightItem]:
        """Return all highlight items on a given page."""
        return self._highlight_items.get(page_index, [])

    def clear_all_highlights(self) -> None:
        """Remove all highlight items from the scene."""
        for items in self._highlight_items.values():
            for item in items:
                self.removeItem(item)
        self._highlight_items.clear()

    # ------------------------------------------------------------------
    # TextBox tracking
    # ------------------------------------------------------------------

    def get_textboxes_for_page(self, page_index: int) -> list[TextBoxItem]:
        """Return all text box items on a given page."""
        return self._text_box_items.get(page_index, [])

    def deselect_all_textboxes(self) -> None:
        """Deselect all TextBoxItems in the scene."""
        changed = False
        for page_items in self._text_box_items.values():
            for box in list(page_items):  # copy: set_selected_custom may remove
                if box._is_editing or box._is_selected_custom:
                    box.stop_editing()
                    box.set_selected_custom(False)
                    changed = True
        if changed:
            self.update()

    def request_tool_switch(self, tool_name: str) -> None:
        """Emit tool_switch_requested signal (wired in viewer_window)."""
        self.tool_switch_requested.emit(tool_name)

    # ------------------------------------------------------------------
    # Unified item registry
    # ------------------------------------------------------------------

    def remove_item_from_registry(self, item: object) -> None:
        """Remove an annotation item from the internal tracking registry.

        Uses item.page_index for O(1) dict lookup instead of scanning
        all pages.  Falls back to full scan if the direct lookup fails
        (e.g. after page reordering where page_index may be stale).

        Idempotent – no error if item is not in registry.
        Does NOT call removeItem on the scene – the caller handles that.
        """
        page_idx = getattr(item, '_page_index', -1)

        if isinstance(item, StrokeItem):
            registry = self._stroke_items
        elif isinstance(item, HighlightItem):
            registry = self._highlight_items
        elif isinstance(item, TextBoxItem):
            registry = self._text_box_items
        elif isinstance(item, ShapeItem):
            registry = self._shape_items
        elif isinstance(item, ImageItem):
            registry = self._image_items
        else:
            return

        # Fast path: direct lookup via page_index
        if page_idx >= 0 and page_idx in registry:
            try:
                registry[page_idx].remove(item)
                return
            except ValueError:
                pass

        # Slow fallback: scan all pages (handles stale page_index)
        for page_items in registry.values():
            try:
                page_items.remove(item)
                return
            except ValueError:
                continue

    def add_item_to_registry(self, item: object) -> None:
        """Add an annotation item to the correct tracking registry.

        Robust: prevents duplicate insertions and validates page_index.
        """
        if isinstance(item, StrokeItem):
            page_idx = item.page_index
            if page_idx < 0:
                return
            existing = self._stroke_items.get(page_idx, [])
            if item not in existing:
                existing.append(item)
                self._stroke_items[page_idx] = existing
        elif isinstance(item, HighlightItem):
            page_idx = item.page_index
            if page_idx < 0:
                return
            existing = self._highlight_items.get(page_idx, [])
            if item not in existing:
                existing.append(item)
                self._highlight_items[page_idx] = existing
        elif isinstance(item, TextBoxItem):
            page_idx = item.page_index
            if page_idx < 0:
                return
            existing = self._text_box_items.get(page_idx, [])
            if item not in existing:
                existing.append(item)
                self._text_box_items[page_idx] = existing
        elif isinstance(item, ShapeItem):
            page_idx = item.page_index
            if page_idx < 0:
                return
            existing = self._shape_items.get(page_idx, [])
            if item not in existing:
                existing.append(item)
                self._shape_items[page_idx] = existing
        elif isinstance(item, ImageItem):
            page_idx = item.page_index
            if page_idx < 0:
                return
            existing = self._image_items.get(page_idx, [])
            if item not in existing:
                existing.append(item)
                self._image_items[page_idx] = existing

    def get_all_annotation_items(self) -> list:
        """Return all annotation items from all pages."""
        result = []
        for items in self._stroke_items.values():
            result.extend(items)
        for items in self._highlight_items.values():
            result.extend(items)
        for items in self._text_box_items.values():
            result.extend(items)
        for items in self._shape_items.values():
            result.extend(items)
        for items in self._image_items.values():
            result.extend(items)
        return result
