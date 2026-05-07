"""Icon factory – creates crisp, resolution-independent SVG icons.

Uses Lucide-style SVG paths (24×24 viewBox, stroke-based, round caps/joins).
New icons can be registered at runtime via IconFactory.register().

Usage:
    from ui.components.icon_factory import IconFactory

    icon = IconFactory.create("pen")
    icon_blue = IconFactory.create("pen", color="#3B7BF5")
    btn.setIcon(icon)

Adding new icons:
    IconFactory.register("my_tool", '<path d="M5 12h14"/>')
"""

from PySide6.QtCore import Qt, QByteArray, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


class IconFactory:
    """Factory for creating SVG-based icons with Lucide styling.

    All icons follow Lucide conventions:
    - viewBox: 0 0 24 24
    - fill: none
    - stroke: configurable color (default #cccccc)
    - stroke-width: 2
    - stroke-linecap: round
    - stroke-linejoin: round

    Icons are rendered at 2× native size for HiDPI crispness and
    have their devicePixelRatio set accordingly.
    """

    _SVG_TEMPLATE: str = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="24" height="24" viewBox="0 0 24 24" '
        'fill="none" stroke="{color}" '
        'stroke-width="{stroke_width}" '
        'stroke-linecap="round" stroke-linejoin="round">'
        "{elements}"
        "</svg>"
    )

    # Registry: icon name → SVG inner elements
    _REGISTRY: dict[str, str] = {}

    _ICON_CACHE: dict[tuple, QIcon] = {}
    _PIXMAP_CACHE: dict[tuple, QPixmap] = {}

    @classmethod
    def register(cls, name: str, svg_elements: str) -> None:
        """Register a new icon by name with SVG inner elements.

        Args:
            name: Unique icon identifier (e.g., "pen", "eraser").
            svg_elements: SVG elements string (paths, lines, circles, etc.)
                using the 24×24 coordinate system.
        """
        cls._REGISTRY[name] = svg_elements

    @classmethod
    def create(
        cls,
        name: str,
        color: str = "#cccccc",
        size: int = 24,
        stroke_width: float = 2.0,
    ) -> QIcon:
        """Create a QIcon from a registered icon name.

        Args:
            name: Registered icon identifier.
            color: Stroke color as hex string.
            size: Logical icon size in pixels.
            stroke_width: SVG stroke width (default 2.0 for Lucide style).

        Returns:
            QIcon rendered at HiDPI resolution.
        """
        from core.app_settings import AppSettings
        if AppSettings.get_theme() == "light":
            if color in ("#cccccc", "#ffffff", "#888888", "#555555"):
                color = "#1a1a1a"
                
        elements = cls._REGISTRY.get(name, "")
        if not elements:
            return QIcon()

        key = (name, color, size, stroke_width)
        if key in cls._ICON_CACHE:
            return cls._ICON_CACHE[key]

        svg_str = cls._SVG_TEMPLATE.format(
            color=color,
            stroke_width=stroke_width,
            elements=elements,
        )

        # Determine render scale for crisp icons
        dpr = cls._get_device_pixel_ratio()
        render_size = int(size * dpr)

        pixmap = QPixmap(render_size, render_size)
        pixmap.fill(Qt.GlobalColor.transparent)

        renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))
        if renderer.isValid():
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            renderer.render(painter, QRectF(0, 0, render_size, render_size))
            painter.end()

        pixmap.setDevicePixelRatio(dpr)
        icon = QIcon(pixmap)
        cls._ICON_CACHE[key] = icon
        return icon

    @classmethod
    def create_pixmap(
        cls,
        name: str,
        color: str = "#cccccc",
        size: int = 24,
        stroke_width: float = 2.0,
    ) -> QPixmap:
        """Create a QPixmap from a registered icon name.

        Same as create() but returns a QPixmap instead of QIcon.
        Useful for labels or custom painting.

        Args:
            name: Registered icon identifier.
            color: Stroke color as hex string.
            size: Logical icon size in pixels.
            stroke_width: SVG stroke width.

        Returns:
            QPixmap rendered at HiDPI resolution.
        """
        from core.app_settings import AppSettings
        if AppSettings.get_theme() == "light":
            if color in ("#cccccc", "#ffffff", "#888888", "#555555"):
                color = "#1a1a1a"

        elements = cls._REGISTRY.get(name, "")
        if not elements:
            return QPixmap()

        key = (name, color, size, stroke_width)
        if key in cls._PIXMAP_CACHE:
            return cls._PIXMAP_CACHE[key]

        svg_str = cls._SVG_TEMPLATE.format(
            color=color,
            stroke_width=stroke_width,
            elements=elements,
        )

        dpr = cls._get_device_pixel_ratio()
        render_size = int(size * dpr)

        pixmap = QPixmap(render_size, render_size)
        pixmap.fill(Qt.GlobalColor.transparent)

        renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))
        if renderer.isValid():
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            renderer.render(painter, QRectF(0, 0, render_size, render_size))
            painter.end()

        pixmap.setDevicePixelRatio(dpr)
        cls._PIXMAP_CACHE[key] = pixmap
        return pixmap

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the icon and pixmap caches."""
        cls._ICON_CACHE.clear()
        cls._PIXMAP_CACHE.clear()

    @classmethod
    def available_icons(cls) -> list[str]:
        """Return a list of all registered icon names."""
        return sorted(cls._REGISTRY.keys())

    @staticmethod
    def _get_device_pixel_ratio() -> float:
        """Return device pixel ratio, or 2.0 as minimum for crisp rendering."""
        app = QApplication.instance()
        if app is not None:
            screen = app.primaryScreen()
            if screen is not None:
                return max(screen.devicePixelRatio(), 2.0)
        return 2.0


# ======================================================================
# Built-in Lucide icon registration
# ======================================================================

def _register_builtins() -> None:
    """Register all built-in Lucide-style icons."""
    r = IconFactory.register

    # ---- Tool icons ----

    # Type / Text (text input mode)
    r(
        "text",
        '<polyline points="4 7 4 4 20 4 20 7"/>'
        '<line x1="9" x2="15" y1="20" y2="20"/>'
        '<line x1="12" x2="12" y1="4" y2="20"/>',
    )

    # Hand (pan / grab tool) – Lucide "Hand"
    r(
        "hand",
        '<path d="m4 4 7.07 17 2.51-7.39L21 11.07z"/>',
    )

    # PenLine (drawing tool) – Lucide "PenLine"
    r(
        "pen",
        '<path d="M12 20h9"/>'
        '<path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    )

    # Highlighter – Lucide "Highlighter"
    r(
        "highlighter",
        '<path d="m9 11-6 6v3h9l3-3"/>'
        '<path d="m22 12-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2'
        'a2 2 0 0 1 0-2.8L14 4"/>',
    )

    # Eraser – Lucide "Eraser"
    r(
        "eraser",
        '<path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.9-9.9'
        'c1-1 2.5-1 3.4 0l5.3 5.3c1 1 1 2.5 0 3.4L11.7 21"/>'
        '<path d="M22 21H7"/>'
        '<path d="m5 11 9 9"/>',
    )

    # Selection (mouse pointer) – Lucide "Mouse Pointer"
    r(
        "selection",
        '<path d="M12.034 12.681a.498.498 0 0 1 .647-.647l9 3.5a.5.5 0 0 1-.033.943l-3.444 1.068a1 1 0 0 0-.66.66l-1.067 3.443a.5.5 0 0 1-.943.033z"/>'
        '<path d="M5 3a2 2 0 0 0-2 2"/>'
        '<path d="M19 3a2 2 0 0 1 2 2"/>'
        '<path d="M5 21a2 2 0 0 1-2-2"/>'
        '<path d="M9 3h1"/>'
        '<path d="M9 21h2"/>'
        '<path d="M14 3h1"/>'
        '<path d="M3 9v1"/>'
        '<path d="M21 9v2"/>'
        '<path d="M3 14v1"/>',
    )

    # ---- UI icons (for future use) ----

    # Plus (add color)
    r("plus", '<path d="M5 12h14"/><path d="M12 5v14"/>')

    # ChevronLeft (back navigation)
    r("chevron_left", '<path d="m15 18-6-6 6-6"/>')

    # ChevronRight
    r("chevron_right", '<path d="m9 18 6-6-6-6"/>')

    # ChevronUp
    r("chevron_up", '<path d="m18 15-6-6-6 6"/>')

    # ChevronDown
    r("chevron_down", '<path d="m6 9 6 6 6-6"/>')

    # Undo – Lucide "Undo2"
    r(
        "undo",
        '<path d="M9 14 4 9l5-5"/>'
        '<path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
    )

    # Redo – Lucide "Redo2"
    r(
        "redo",
        '<path d="m15 14 5-5-5-5"/>'
        '<path d="M20 9H9.5A5.5 5.5 0 0 0 4 14.5A5.5 5.5 0 0 0 9.5 20H13"/>',
    )

    # Search – Lucide "Search"
    r(
        "search",
        '<circle cx="11" cy="11" r="8"/>'
        '<path d="m21 21-4.3-4.3"/>',
    )

    # Settings – Lucide "Settings"
    r(
        "settings",
        '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25'
        'a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38'
        'a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51'
        'a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38'
        'a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25'
        'a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18'
        'a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08'
        'a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08'
        'a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09'
        'a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08'
        'a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>'
        '<circle cx="12" cy="12" r="3"/>',
    )

    # Folder – Lucide "Folder"
    r(
        "folder",
        '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9'
        'a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4'
        'a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    )

    # Globe – Lucide "Globe"
    r(
        "globe",
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M12 2a14.5 14.5 0 0 0 0 20'
        ' 14.5 14.5 0 0 0 0-20"/>'
        '<path d="M2 12h20"/>',
    )

    # Monitor – Lucide "Monitor"
    r(
        "monitor",
        '<rect width="20" height="14" x="2" y="3" rx="2"/>'
        '<path d="M8 21h8"/>'
        '<path d="M12 17v4"/>',
    )

    # Moon – Lucide "Moon"
    r(
        "moon",
        '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    )

    # Sun – Lucide "Sun"
    r(
        "sun",
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2M12 20v2'
        'M4.93 4.93l1.41 1.41'
        'M17.66 17.66l1.41 1.41'
        'M2 12h2M20 12h2'
        'M6.34 17.66l-1.41 1.41'
        'M19.07 4.93l-1.41 1.41"/>',
    )

    # FolderOpen – Lucide "FolderOpen"
    r(
        "folder_open",
        '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20'
        'a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95'
        ' 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 0 2-2h3.9'
        'a2 2 0 0 1 1.69.9l.81 1.2A2 2 0 0 0 12.11 6H18'
        'a2 2 0 0 1 2 2v2"/>',
    )

    # Clock – Lucide "Clock"
    r(
        "clock",
        '<circle cx="12" cy="12" r="10"/>'
        '<polyline points="12 6 12 12 16 14"/>',
    )

    # LayoutGrid – Lucide "LayoutGrid"
    r(
        "layout_grid",
        '<rect width="7" height="7" x="3" y="3" rx="1"/>'
        '<rect width="7" height="7" x="14" y="3" rx="1"/>'
        '<rect width="7" height="7" x="14" y="14" rx="1"/>'
        '<rect width="7" height="7" x="3" y="14" rx="1"/>',
    )

    # File – Lucide "File"
    r(
        "file",
        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12'
        'a2 2 0 0 0 2-2V7Z"/>'
        '<path d="M14 2v4a2 2 0 0 0 2 2h4"/>',
    )

    # Download / Save – Lucide "Download"
    r(
        "download",
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="7 10 12 15 17 10"/>'
        '<line x1="12" x2="12" y1="15" y2="3"/>',
    )

    # Trash – Lucide "Trash2"
    r(
        "trash",
        '<path d="M3 6h18"/>'
        '<path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>'
        '<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>'
        '<line x1="10" x2="10" y1="11" y2="17"/>'
        '<line x1="14" x2="14" y1="11" y2="17"/>',
    )

    # ZoomIn – Lucide "ZoomIn"
    r(
        "zoom_in",
        '<circle cx="11" cy="11" r="8"/>'
        '<line x1="21" x2="16.65" y1="21" y2="16.65"/>'
        '<line x1="11" x2="11" y1="8" y2="14"/>'
        '<line x1="8" x2="14" y1="11" y2="11"/>',
    )

    # ZoomOut – Lucide "ZoomOut"
    r(
        "zoom_out",
        '<circle cx="11" cy="11" r="8"/>'
        '<line x1="21" x2="16.65" y1="21" y2="16.65"/>'
        '<line x1="8" x2="14" y1="11" y2="11"/>',
    )

    # MoreHorizontal (overflow menu) – Lucide "MoreHorizontal"
    r(
        "more",
        '<circle cx="12" cy="12" r="1"/>'
        '<circle cx="19" cy="12" r="1"/>'
        '<circle cx="5" cy="12" r="1"/>',
    )

    # ---- FormattingBar icons ----

    # AlignLeft – Lucide "AlignLeft"
    r(
        "align_left",
        '<line x1="21" x2="3" y1="6" y2="6"/>'
        '<line x1="15" x2="3" y1="12" y2="12"/>'
        '<line x1="17" x2="3" y1="18" y2="18"/>',
    )

    # AlignCenter – Lucide "AlignCenter"
    r(
        "align_center",
        '<line x1="21" x2="3" y1="6" y2="6"/>'
        '<line x1="17" x2="7" y1="12" y2="12"/>'
        '<line x1="19" x2="5" y1="18" y2="18"/>',
    )

    # AlignRight – Lucide "AlignRight"
    r(
        "align_right",
        '<line x1="21" x2="3" y1="6" y2="6"/>'
        '<line x1="21" x2="9" y1="12" y2="12"/>'
        '<line x1="21" x2="7" y1="18" y2="18"/>',
    )

    # List – Lucide "List"
    r(
        "list",
        '<line x1="8" x2="21" y1="6" y2="6"/>'
        '<line x1="8" x2="21" y1="12" y2="12"/>'
        '<line x1="8" x2="21" y1="18" y2="18"/>'
        '<line x1="3" x2="3.01" y1="6" y2="6"/>'
        '<line x1="3" x2="3.01" y1="12" y2="12"/>'
        '<line x1="3" x2="3.01" y1="18" y2="18"/>',
    )

    # Shape tool icons
    IconFactory.register(
        "shape",
        '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>',
    )
    IconFactory.register(
        "shape_rect",
        '<rect x="3" y="3" width="18" height="18"/>',
    )
    IconFactory.register(
        "shape_rounded_rect",
        '<rect x="3" y="3" width="18" height="18" rx="4" ry="4"/>',
    )
    IconFactory.register(
        "shape_ellipse",
        '<ellipse cx="12" cy="12" rx="10" ry="7"/>',
    )
    IconFactory.register(
        "shape_line",
        '<line x1="5" y1="19" x2="19" y2="5"/>',
    )
    IconFactory.register(
        "shape_arrow",
        '<line x1="5" y1="19" x2="19" y2="5"/>'
        '<polyline points="9 5 19 5 19 15"/>',
    )
    IconFactory.register(
        "shape_triangle",
        '<polygon points="12 3 22 21 2 21"/>',
    )

    # FilePlus – Lucide "FilePlus2"
    IconFactory.register(
        "file_plus",
        '<path d="M4 22h14a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v4"/>'
        '<path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
        '<path d="M3 15h6"/>'
        '<path d="M6 12v6"/>',
    )

    # Info – Lucide "Info"
    IconFactory.register(
        "info",
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M12 16v-4"/>'
        '<path d="M12 8h.01"/>',
    )

    # FolderX – Lucide "FolderX" (empty folder state)
    IconFactory.register(
        "folder_x",
        '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9'
        'a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4'
        'a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>'
        '<path d="m9.5 10.5 5 5"/>'
        '<path d="m14.5 10.5-5 5"/>',
    )

    # X (close) – Lucide "X"
    IconFactory.register(
        "x",
        '<path d="M18 6 6 18"/>'
        '<path d="m6 6 12 12"/>',
    )
    
    # Square – Lucide "Square"
    IconFactory.register(
        "square",
        '<rect width="18" height="18" x="3" y="3" rx="2"/>',
    )

    # CheckSquare – Lucide "CheckSquare"
    IconFactory.register(
        "check_square",
        '<rect width="18" height="18" x="3" y="3" rx="2"/>'
        '<path d="m9 12 2 2 4-4"/>',
    )

    # Copy – Lucide "Copy"
    IconFactory.register(
        "copy",
        '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>'
        '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    )
    
    # Clipboard (paste) – Lucide "ClipboardPaste"
    IconFactory.register(
        "clipboard",
        '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/>'
        '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>',
    )

    # CopyPlus (duplicate) – Lucide "CopyPlus"
    IconFactory.register(
        "copy_plus",
        '<line x1="15" x2="15" y1="12" y2="18"/>'
        '<line x1="12" x2="18" y1="15" y2="15"/>'
        '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>'
        '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    )

    # FolderInput (move) – Lucide "FolderInput"
    IconFactory.register(
        "folder_input",
        '<path d="M2 9V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H20a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H2"/>'
        '<path d="M2 13h10"/>'
        '<path d="m9 16 3-3-3-3"/>',
    )



# Run registration at module import time
_register_builtins()
