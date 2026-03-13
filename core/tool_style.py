"""Tool style data – shared drawing parameters for all tools."""

from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


@dataclass
class ToolStyle:
    """Drawing style parameters used by tools and stroke items.

    Attributes:
        color: Stroke color (default black).
        width: Stroke width in pixels (default 3.0).
        opacity: Stroke opacity 0.0–1.0 (default 1.0).
        tool_type: Tool identifier string.
        font_family: Font family name for text tool.
        font_size: Font size in points for text tool.
        bold: Bold flag for text tool.
        italic: Italic flag for text tool.
    """

    PRESET_WIDTHS: list[float] = field(
        default_factory=lambda: [2.0, 4.0, 8.0], init=False, repr=False
    )

    color: QColor = field(default_factory=lambda: QColor("#1a1a1a"))
    width: float = 3.0
    opacity: float = 1.0
    tool_type: str = "pen"
    font_family: str = "Arial"
    font_size: int = 12
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft

    def copy(self) -> "ToolStyle":
        """Return a shallow copy of this style."""
        return ToolStyle(
            color=QColor(self.color),
            width=self.width,
            opacity=self.opacity,
            tool_type=self.tool_type,
            font_family=self.font_family,
            font_size=self.font_size,
            bold=self.bold,
            italic=self.italic,
            underline=self.underline,
            strikethrough=self.strikethrough,
            alignment=self.alignment,
        )

    def to_dict(self) -> dict:
        """Serialize to a dictionary (color as hex string).

        Returns:
            Dictionary with all style fields.
        """
        return {
            "color": self.color.name(),
            "width": self.width,
            "opacity": self.opacity,
            "tool_type": self.tool_type,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "strikethrough": self.strikethrough,
            "alignment": int(self.alignment),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolStyle":
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with style fields.

        Returns:
            A new ToolStyle instance.
        """
        return cls(
            color=QColor(data.get("color", "#1a1a1a")),
            width=float(data.get("width", 3.0)),
            opacity=float(data.get("opacity", 1.0)),
            tool_type=str(data.get("tool_type", "pen")),
            font_family=str(data.get("font_family", "Arial")),
            font_size=int(data.get("font_size", 12)),
            bold=bool(data.get("bold", False)),
            italic=bool(data.get("italic", False)),
            underline=bool(data.get("underline", False)),
            strikethrough=bool(data.get("strikethrough", False)),
            alignment=Qt.AlignmentFlag(int(data.get("alignment", int(Qt.AlignmentFlag.AlignLeft)))),
        )
