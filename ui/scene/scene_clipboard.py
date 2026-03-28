"""Scene clipboard mixin – delete, copy, cut, paste and serialization."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QPointF

from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem
from items.text_box_item import TextBoxItem
from items.shape_item import ShapeItem


class SceneClipboardMixin:
    """Mixin providing clipboard actions and item serialization for PageScene.

    Expects the host class to provide:
        _selected_items: set
        clear_selection(): method
        set_selection(): method
        removeItem(): method (from QGraphicsScene)
        addItem(): method (from QGraphicsScene)
        remove_item_from_registry(): method (from SceneRegistryMixin)
        add_item_to_registry(): method (from SceneRegistryMixin)
    """

    # ------------------------------------------------------------------
    # Selection actions (Delete / Copy / Cut / Paste)
    # ------------------------------------------------------------------

    def delete_selected(self) -> None:
        """Delete all selected items via undoable command."""
        items = list(self._selected_items)
        if not items:
            return
        self.clear_selection()
        for item in items:
            if item.scene() is self:
                self.update(item.sceneBoundingRect())
                self.removeItem(item)
            self.remove_item_from_registry(item)
        from commands.delete_items_command import DeleteItemsCommand
        from core import undo_stack
        cmd = DeleteItemsCommand(items, self)
        undo_stack.push(cmd)

    def copy_selected(self) -> None:
        """Copy selected items to internal clipboard."""
        items = list(self._selected_items)
        if not items:
            return
        self._copy_items_to_clipboard(items)

    def cut_selected(self) -> None:
        """Copy selected items to clipboard, then delete them."""
        items = list(self._selected_items)
        if not items:
            return
        self._copy_items_to_clipboard(items)
        # Remove from scene
        self.clear_selection()
        for item in items:
            if item.scene() is self:
                self.update(item.sceneBoundingRect())
                self.removeItem(item)
            self.remove_item_from_registry(item)
        from commands.delete_items_command import DeleteItemsCommand
        from core import undo_stack
        cmd = DeleteItemsCommand(items, self)
        undo_stack.push(cmd)

    def paste_clipboard(self) -> None:
        """Paste items from internal clipboard into the scene."""
        from app.app_state import AppState
        clipboard = AppState().items_clipboard
        if not clipboard:
            return

        paste_offset = QPointF(16, 16)
        new_items = []
        for entry in clipboard:
            item = self._deserialize_item(entry, paste_offset)
            if item is not None:
                new_items.append(item)

        if not new_items:
            return

        # Add items to scene
        for item in new_items:
            self.addItem(item)
            self.add_item_to_registry(item)

        from commands.paste_items_command import PasteItemsCommand
        from core import undo_stack
        cmd = PasteItemsCommand(new_items, self)
        undo_stack.push(cmd)
        self.set_selection(new_items)

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def _copy_items_to_clipboard(self, items: list) -> None:
        """Serialize items and store in AppState.items_clipboard."""
        from app.app_state import AppState
        entries = []
        for item in items:
            entry = self._serialize_item(item)
            if entry is not None:
                entries.append(entry)
        AppState().items_clipboard = entries

    def _serialize_item(self, item) -> dict | None:
        """Serialize a single item to a dict for clipboard storage."""
        if isinstance(item, StrokeItem):
            path = item._path
            points = []
            for i in range(path.elementCount()):
                el = path.elementAt(i)
                points.append((el.x, el.y))
            return {
                "type": "stroke",
                "points": points,
                "color": item._style.color.name(),
                "width": item._style.width,
                "page_index": item.page_index,
                "pos": (item.pos().x(), item.pos().y()),
            }
        elif isinstance(item, HighlightItem):
            path = item._path
            points = []
            for i in range(path.elementCount()):
                el = path.elementAt(i)
                points.append((el.x, el.y))
            return {
                "type": "highlight",
                "points": points,
                "color": item._style.color.name(),
                "width": item._style.width,
                "page_index": item._page_index,
                "pos": (item.pos().x(), item.pos().y()),
            }
        elif isinstance(item, TextBoxItem):
            r = item.get_rect()
            return {
                "type": "textbox",
                "html": item._document.toHtml(),
                "rect": (r.x(), r.y(), r.width(), r.height()),
                "rotation": item.rotation(),
                "page_index": item.page_index,
                "pos": (item.pos().x(), item.pos().y()),
            }
        elif isinstance(item, ShapeItem):
            return item.to_dict()
        return None

    def _deserialize_item(self, entry: dict, offset: QPointF):
        """Reconstruct an item from serialized clipboard data."""
        from PySide6.QtGui import QPainterPath, QColor
        from core.tool_style import ToolStyle

        item_type = entry.get("type")
        ox, oy = entry["pos"]
        new_pos = QPointF(ox + offset.x(), oy + offset.y())

        if item_type == "stroke":
            path = QPainterPath()
            pts = entry["points"]
            if pts:
                path.moveTo(pts[0][0], pts[0][1])
                for px, py in pts[1:]:
                    path.lineTo(px, py)
            style = ToolStyle(
                color=QColor(entry["color"]),
                width=entry["width"],
            )
            item = StrokeItem(
                path=path,
                style=style,
                page_index=entry["page_index"],
            )
            item.setPos(new_pos)
            return item

        elif item_type == "highlight":
            path = QPainterPath()
            pts = entry["points"]
            if pts:
                path.moveTo(pts[0][0], pts[0][1])
                for px, py in pts[1:]:
                    path.lineTo(px, py)
            style = ToolStyle(
                color=QColor(entry["color"]),
                width=entry["width"],
            )
            item = HighlightItem(
                style=style,
                page_index=entry["page_index"],
            )
            item._path = path
            item.setPos(new_pos)
            return item

        elif item_type == "textbox":
            rx, ry, rw, rh = entry["rect"]
            style = ToolStyle()
            item = TextBoxItem(
                rect=QRectF(rx, ry, rw, rh),
                style=style,
                page_index=entry["page_index"],
            )
            item._document.setHtml(entry["html"])
            item.setRotation(entry.get("rotation", 0.0))
            item.setPos(new_pos)
            return item

        elif item_type == "shape":
            from core.shape_style import ShapeStyle
            item = ShapeItem.from_dict(entry)
            item.setPos(new_pos)
            return item

        return None
