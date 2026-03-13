"""Items layer – custom QGraphicsItem subclasses for annotations."""

from .stroke_item import StrokeItem
from .highlight_item import HighlightItem
from .eraser_cursor_item import EraserCursorItem
from .handle_item import ResizeHandleItem, HandlePosition
from .text_box_item import TextBoxItem
from .rotate_handle_item import RotateHandleItem
from .move_handle_item import MoveHandleItem
from .selection_overlay_item import SelectionOverlayItem
from .shape_item import ShapeItem

__all__ = [
    "StrokeItem", "HighlightItem", "EraserCursorItem",
    "ResizeHandleItem", "HandlePosition", "TextBoxItem",
    "RotateHandleItem", "MoveHandleItem",
    "SelectionOverlayItem",
    "ShapeItem",
]
