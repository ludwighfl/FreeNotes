"""Application state singleton – holds all shared state data."""

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor

from core.tool_style import ToolStyle


class AppState(QObject):
    """Singleton application state. Holds current document, page, zoom, and tool data.

    Signals:
        page_changed(int): Emitted when the current page index changes.
        zoom_changed(float): Emitted when the zoom factor changes.
        tool_changed(str): Emitted when the active tool changes.
        style_changed(ToolStyle): Emitted when the tool style changes.
    """

    page_changed = Signal(int)
    zoom_changed = Signal(float)
    tool_changed = Signal(str)
    style_changed = Signal(object)  # ToolStyle (object for QObject signal compat)

    _instance: "AppState | None" = None

    def __new__(cls) -> "AppState":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        super().__init__()
        self._initialized: bool = True

        self._current_pdf_path: Path | None = None
        self._current_page: int = 0
        self._zoom_factor: float = 1.0
        self._total_pages: int = 0
        self._active_tool_name: str = "hand"
        self._tool_style: ToolStyle = ToolStyle()
        self.clipboard_box = None  # TextBoxItem clone for Copy/Cut
        self.items_clipboard: list[dict] = []  # Serialized items for Copy/Paste

        # Shape tool state
        from core.shape_style import ShapeType
        self.active_shape_type: ShapeType = ShapeType.RECT
        self.shape_fill_color: QColor = QColor(255, 255, 255, 0)  # transparent
        self.shape_stroke_color: QColor = QColor("#3B7BF5")
        self.current_stroke_width: float = 2.0

        # Save/load state
        self.freenotes_path: str | None = None
        self.is_modified: bool = False

    # --- current_pdf_path ---
    @property
    def current_pdf_path(self) -> Path | None:
        return self._current_pdf_path

    @current_pdf_path.setter
    def current_pdf_path(self, value: Path | None) -> None:
        self._current_pdf_path = value

    # --- current_page ---
    @property
    def current_page(self) -> int:
        return self._current_page

    @current_page.setter
    def current_page(self, value: int) -> None:
        if self._current_page != value:
            self._current_page = value
            self.page_changed.emit(value)

    # --- zoom_factor ---
    @property
    def zoom_factor(self) -> float:
        return self._zoom_factor

    @zoom_factor.setter
    def zoom_factor(self, value: float) -> None:
        if self._zoom_factor != value:
            self._zoom_factor = value
            self.zoom_changed.emit(value)

    # --- total_pages ---
    @property
    def total_pages(self) -> int:
        return self._total_pages

    @total_pages.setter
    def total_pages(self, value: int) -> None:
        self._total_pages = value

    # --- active_tool_name ---
    @property
    def active_tool_name(self) -> str:
        return self._active_tool_name

    @active_tool_name.setter
    def active_tool_name(self, value: str) -> None:
        if self._active_tool_name != value:
            self._active_tool_name = value
            self.tool_changed.emit(value)

    # --- tool_style ---
    @property
    def tool_style(self) -> ToolStyle:
        return self._tool_style

    @tool_style.setter
    def tool_style(self, value: ToolStyle) -> None:
        self._tool_style = value
        self.style_changed.emit(value)

    def update_style(self, **kwargs: object) -> None:
        """Update specific fields of the current tool style.

        Emits style_changed after updating.

        Args:
            **kwargs: Fields to update (color, width, opacity, tool_type,
                      font_family, font_size, bold, italic).
        """
        if "color" in kwargs:
            self._tool_style.color = kwargs["color"]
        if "width" in kwargs:
            self._tool_style.width = kwargs["width"]
        if "opacity" in kwargs:
            self._tool_style.opacity = kwargs["opacity"]
        if "tool_type" in kwargs:
            self._tool_style.tool_type = kwargs["tool_type"]
        if "font_family" in kwargs:
            self._tool_style.font_family = kwargs["font_family"]
        if "font_size" in kwargs:
            self._tool_style.font_size = kwargs["font_size"]
        if "bold" in kwargs:
            self._tool_style.bold = kwargs["bold"]
        if "italic" in kwargs:
            self._tool_style.italic = kwargs["italic"]
        if "underline" in kwargs:
            self._tool_style.underline = kwargs["underline"]
        if "strikethrough" in kwargs:
            self._tool_style.strikethrough = kwargs["strikethrough"]
        if "alignment" in kwargs:
            self._tool_style.alignment = kwargs["alignment"]
        self.style_changed.emit(self._tool_style)

    def reset(self) -> None:
        """Reset state to defaults."""
        self._current_pdf_path = None
        self._current_page = 0
        self._zoom_factor = 1.0
        self._total_pages = 0
        self._active_tool_name = "hand"
        self._tool_style = ToolStyle()
