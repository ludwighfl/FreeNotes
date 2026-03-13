"""Command for resizing multiple selected items via their selection overlay."""

from PySide6.QtGui import QUndoCommand

from items.selection_overlay_item import SelectionOverlayItem


class ResizeItemsCommand(QUndoCommand):
    """Command to undo/redo the resizing of multiple items."""

    def __init__(
        self,
        overlay_item: SelectionOverlayItem,
        old_state: tuple,
        new_state: tuple,
        scene,
    ) -> None:
        super().__init__("Elemente skalieren")
        self._overlay_item = overlay_item
        self._old_state = old_state
        self._new_state = new_state
        self._scene = scene
        self._is_first_redo = True

    def undo(self) -> None:
        self._overlay_item.set_path_state(self._old_state[0], self._old_state[1])
        if hasattr(self._scene, "_update_selection_overlay"):
            self._scene._update_selection_overlay()

    def redo(self) -> None:
        if self._is_first_redo:
            self._is_first_redo = False
            return
        self._overlay_item.set_path_state(self._new_state[0], self._new_state[1])
        if hasattr(self._scene, "_update_selection_overlay"):
            self._scene._update_selection_overlay()
