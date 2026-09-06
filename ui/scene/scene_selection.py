"""Mixin for handling multi-item selections and bounding boxes."""

from __future__ import annotations
from typing import TYPE_CHECKING
from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem
from items.text_box_item import TextBoxItem
from items.shape_item import ShapeItem
from items.image_item import ImageItem
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
        """Mark item as selected."""
        if hasattr(item, "set_selected_custom"):
            item.set_selected_custom(True)
        elif hasattr(item, "set_selected"):
            item.set_selected(True)

    def _deselect_item(self, item) -> None:
        """Remove selection visual from item."""
        if hasattr(item, "set_selected_custom"):
            item.set_selected_custom(False)
        elif hasattr(item, "set_selected"):
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
        """Refresh the selection overlay bounding box."""
        items = list(self._selected_items)
        if items:
            self._ensure_overlay().attach(items, self)
        else:
            self._ensure_overlay().setVisible(False)

    def _on_selection_changed(self) -> None:
        """React to selection changes: update individual visual frames and selection overlay."""
        items = list(self._selected_items)
        overlay = self._ensure_overlay()
        if items:
            for item in items:
                self._select_item(item)
            overlay.attach(items, self)
        else:
            overlay.setVisible(False)

    def rotate_selected_90(self, delta_angle: float = 90.0) -> None:
        """Rotate selected items by 90 degrees (+90 or -90) with full undo/redo support and overlay AABB update."""
        if not self._selected_items:
            return

        from items.interactive_item import IInteractiveItem
        managed = [i for i in self._selected_items if isinstance(i, IInteractiveItem)]
        if not managed:
            return

        from commands.transform_items_command import TransformItemsCommand
        from core.undo_stack import get_stack

        before_state = {item: item.capture_state() for item in managed if hasattr(item, "capture_state")}

        overlay = self._ensure_overlay()
        overlay.apply_group_rotation(delta_angle)

        after_state = {item: item.capture_state() for item in managed if hasattr(item, "capture_state")}

        cmd = TransformItemsCommand(
            items_before=before_state,
            items_after=after_state,
            scene=self,
            text=f"Um {int(delta_angle)}° drehen",
        )
        get_stack().push(cmd)
