"""Mixin for handling multi-item selections and bounding boxes."""

from __future__ import annotations
from typing import TYPE_CHECKING
from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem
from items.text_box_item import TextBoxItem
from items.shape_item import ShapeItem
from items.selection_overlay_item import SelectionOverlayItem

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class SceneSelectionMixin:
    """Mixin for managing selections and the multi-selection overlay.

    Expects the host class to provide:
        _selected_items: set
        _selection_overlay: SelectionOverlayItem
        _bbox_handle_manager: BoundingBoxHandleManager
        selection_changed: Signal
        addItem(): method
    """

    def set_selection(self, items: list) -> None:
        """Replace the entire selection with *items*."""
        old = set(self._selected_items)
        self._selected_items.clear()
        for item in old:
            self._deselect_item(item)
        for item in items:
            self._select_item(item)
            self._selected_items.add(item)
        self._update_selection_overlay()
        self.selection_changed.emit()

    def add_to_selection(self, item) -> None:
        """Add a single item to the selection."""
        if item not in self._selected_items:
            self._select_item(item)
            self._selected_items.add(item)
            self._update_selection_overlay()
            self.selection_changed.emit()

    def remove_from_selection(self, item) -> None:
        """Remove a single item from the selection."""
        if item in self._selected_items:
            self._deselect_item(item)
            self._selected_items.discard(item)
            self._update_selection_overlay()
            self.selection_changed.emit()

    def clear_selection(self) -> None:
        """Deselect everything."""
        for item in set(self._selected_items):
            self._deselect_item(item)
        self._selected_items.clear()
        self._ensure_overlay().setVisible(False)
        self.selection_changed.emit()

    def get_selected_items(self) -> list:
        """Return a snapshot of the current selection."""
        return list(self._selected_items)

    def _select_item(self, item) -> None:
        """Mark *item* as selected (visual feedback) if it is the ONLY selected item.
        If there are multiple selected items, individual markers are hidden.
        """
        if len(self._selected_items) >= 2:
            return  # Will be hidden by _on_selection_changed

        if isinstance(item, TextBoxItem):
            item.set_selected_custom(True)
        elif isinstance(item, ShapeItem):
            item.set_selected_custom(True)
        elif isinstance(item, (StrokeItem, HighlightItem)):
            item.set_selected(True)

    def _deselect_item(self, item) -> None:
        """Remove selection visual from *item*."""
        if isinstance(item, TextBoxItem):
            item.set_selected_custom(False)
        elif isinstance(item, ShapeItem):
            item.set_selected_custom(False)
        elif isinstance(item, (StrokeItem, HighlightItem)):
            item.set_selected(False)

    def _ensure_overlay(self) -> SelectionOverlayItem:
        """Return the selection overlay, recreating it if the C++ side was deleted."""
        try:
            self._selection_overlay.isVisible()  # probe C++ object
        except RuntimeError:
            self._selection_overlay = SelectionOverlayItem()
            self.addItem(self._selection_overlay)
            self._selection_overlay.setVisible(False)
        return self._selection_overlay

    def _update_selection_overlay(self) -> None:
        """Refresh the multi-selection overlay bounding box."""
        self._ensure_overlay().update_from_items(
            list(self._selected_items), self)
        self._bbox_handle_manager.reposition()

    def _on_selection_changed(self) -> None:
        """React to selection changes: update individual visuals and bounding box resize handles."""
        items = list(self._selected_items)
        count = len(items)

        # 1. Update individual item visuals based on selection count
        if count >= 2:
            # Hide individual borders/handles, the Overlay will show the combined box
            for item in items:
                if isinstance(item, TextBoxItem):
                    item.set_selected_custom(False)
                elif isinstance(item, ShapeItem):
                    item.set_selected_custom(False)
                elif isinstance(item, (StrokeItem, HighlightItem)):
                    item.set_selected(False)
        elif count == 1:
            # Show individual border/handles for the single selected item
            item = items[0]
            if isinstance(item, TextBoxItem):
                item.set_selected_custom(True)
            elif isinstance(item, ShapeItem):
                item.set_selected_custom(True)
            elif isinstance(item, (StrokeItem, HighlightItem)):
                item.set_selected(True)

        # 2. Attach or detach the common bounding box resize handles
        if count == 0:
            self._bbox_handle_manager.detach()
        elif count == 1:
            # ShapeItem has its own handle system
            if isinstance(items[0], (StrokeItem, HighlightItem)):
                self._bbox_handle_manager.attach_to(items[0])
            else:
                self._bbox_handle_manager.detach()
        elif count >= 2:
            # Only allow resizing of multiple items if NO TextBoxItem is selected
            has_textbox = any(isinstance(i, TextBoxItem) for i in items)
            if not has_textbox:
                overlay = self._ensure_overlay()
                self._bbox_handle_manager.attach_to(overlay)
            else:
                self._bbox_handle_manager.detach()
