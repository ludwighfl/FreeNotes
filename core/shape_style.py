"""Shape style — enum + dataclass for geometric shape annotations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from PySide6.QtGui import QColor


class ShapeType(Enum):
    """Supported geometric shape types."""
    RECT = "rect"
    ROUNDED_RECT = "rounded_rect"
    ELLIPSE = "ellipse"
    LINE = "line"
    ARROW = "arrow"
    TRIANGLE = "triangle"


@dataclass
class ShapeStyle:
    """Visual style for a ShapeItem."""

    shape_type: ShapeType = ShapeType.RECT
    fill_color: QColor = field(
        default_factory=lambda: QColor(255, 255, 255, 0))
    stroke_color: QColor = field(
        default_factory=lambda: QColor("#3B7BF5"))
    stroke_width: float = 2.0
    dash: bool = False
    corner_radius: float = 8.0  # Only for ROUNDED_RECT

    def copy(self) -> ShapeStyle:
        """Create a deep copy."""
        return ShapeStyle(
            shape_type=self.shape_type,
            fill_color=QColor(self.fill_color),
            stroke_color=QColor(self.stroke_color),
            stroke_width=self.stroke_width,
            dash=self.dash,
            corner_radius=self.corner_radius,
        )

    def to_dict(self) -> dict:
        """Serialize to dict for storage."""
        return {
            "shape_type": self.shape_type.value,
            "fill_color": self.fill_color.name(QColor.NameFormat.HexArgb),
            "stroke_color": self.stroke_color.name(QColor.NameFormat.HexArgb),
            "stroke_width": self.stroke_width,
            "dash": self.dash,
            "corner_radius": self.corner_radius,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ShapeStyle:
        """Deserialize from dict."""
        return cls(
            shape_type=ShapeType(d["shape_type"]),
            fill_color=QColor(d["fill_color"]),
            stroke_color=QColor(d["stroke_color"]),
            stroke_width=float(d["stroke_width"]),
            dash=bool(d["dash"]),
            corner_radius=float(d.get("corner_radius", 8.0)),
        )
