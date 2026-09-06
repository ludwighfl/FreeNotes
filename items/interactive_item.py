"""Capability interfaces for interactive items on the PDF canvas."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QPointF


class IInteractiveItem:
    """Base interface for all selectable/interactive items."""

    def capture_state(self) -> dict:
        """Snapshot item state for undo/redo."""
        raise NotImplementedError

    def restore_state(self, state: dict) -> None:
        """Restore item state from snapshot."""
        raise NotImplementedError

    def get_rotation_angle(self) -> float:
        """Get rotation angle in degrees."""
        raise NotImplementedError

    def set_rotation_angle(self, angle: float) -> None:
        """Set rotation angle in degrees."""
        raise NotImplementedError

    def get_transform_origin(self) -> QPointF:
        """Get transform origin point."""
        raise NotImplementedError

    def set_transform_origin(self, origin: QPointF) -> None:
        """Set transform origin point."""
        raise NotImplementedError

    def apply_scale(self, sx: float, sy: float, pivot: QPointF) -> None:
        """Scale item around a pivot point (in scene coordinates)."""
        raise NotImplementedError

    def set_selected_custom(self, selected: bool) -> None:
        """Toggle visual selection frame/handles."""
        raise NotImplementedError


class IRectResizable(IInteractiveItem):
    """Capability for items defined by a bounding rectangle (TextBox, Image, rect Shapes)."""

    def get_geometry_rect(self) -> QRectF:
        """Get item geometry rect in scene coordinates."""
        raise NotImplementedError

    def set_geometry_rect(self, rect: QRectF) -> None:
        """Set item geometry rect from scene coordinates."""
        raise NotImplementedError


class ILinearItem(IInteractiveItem):
    """Capability for endpoint-defined items (Lines, Arrows)."""

    def is_linear(self) -> bool:
        """Return True if this item is actually in linear mode (line/arrow)."""
        return True

    def get_start_point(self) -> QPointF:
        """Get start point in scene coordinates."""
        raise NotImplementedError

    def set_start_point(self, pt: QPointF) -> None:
        """Set start point in scene coordinates."""
        raise NotImplementedError

    def get_end_point(self) -> QPointF:
        """Get end point in scene coordinates."""
        raise NotImplementedError

    def set_end_point(self, pt: QPointF) -> None:
        """Set end point in scene coordinates."""
        raise NotImplementedError


class IPathScalable(IInteractiveItem):
    """Capability for path-defined items (StrokeItem, HighlightItem)."""

    def apply_bounding_box_resize(self, new_br: QRectF) -> None:
        """Scale internal path to fit new_br scene bounding rect."""
        raise NotImplementedError
