"""Toolbar widget – tool buttons, 10 customizable color chips, and pen width controls."""

from PySide6.QtCore import Qt, QSize, Signal, QPoint, QTimer
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QToolButton,
    QFrame,
    QButtonGroup,
)

from app.app_state import AppState
from core.tool_style import ToolStyle
from core import undo_stack
from ui.icon_factory import IconFactory
from ui.color_picker_popup import ColorPickerPopup
from ui.toolbar_icons import make_color_icon, make_width_icon
from ui.toolbar_mode_popups import ToolbarModePopupsMixin


class ToolbarWidget(ToolbarModePopupsMixin, QWidget):
    """Horizontal toolbar with Lucide tool icons, 10 customizable color chips,
    and 5 pen width controls.

    Color chips:
    - Single-click selects the color for drawing.
    - Double-click opens the color picker to customize that slot.

    Emits tool_changed when a tool button is clicked, and style_changed
    when a color or width changes.

    Mode popup logic is in ToolbarModePopupsMixin.
    """

    tool_changed = Signal(str)
    style_changed = Signal(object)  # ToolStyle
    eraser_mode_changed = Signal(str)  # "object" or "pixel"
    selection_mode_changed = Signal(str)  # "rect" or "lasso"

    TOOL_IDS: list[str] = ["text", "hand", "pen", "highlighter", "eraser", "selection"]
    TOOL_TOOLTIPS: list[str] = [
        "Text", "Hand", "Pen", "Highlighter", "Eraser",
        "Auswahl (Rechteck / Alt+Drag = Lasso)",
    ]
    ENABLED_TOOLS: set[str] = {"hand", "pen", "highlighter", "eraser", "text", "selection"}

    DEFAULT_COLORS: list[str] = [
        "#1a1a1a", "#555555", "#aaaaaa", "#ffffff",
        "#3B7BF5", "#e53935", "#43a047", "#fdd835",
        "#00bcd4", "#6d4c41",
    ]

    # Visual dot radii (always the same 5 buttons)
    WIDTH_DOT_RADII: list[int] = [1, 2, 4, 6, 8]

    # Mapped values per tool (same 5 buttons, different underlying values)
    PEN_WIDTHS: list[float] = [1.0, 2.0, 4.0, 8.0, 14.0]
    HIGHLIGHTER_WIDTHS: list[float] = [8.0, 16.0, 24.0, 32.0, 48.0]
    ERASER_WIDTHS: list[float] = [10.0, 20.0, 40.0, 60.0, 80.0]

    # Active widths (swapped when tool changes)
    _active_widths: list[float] = PEN_WIDTHS

    # Double-click detection threshold in ms
    DOUBLE_CLICK_MS: int = 300

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("toolbarWidget")
        self._app_state: AppState = AppState()
        self._popup: ColorPickerPopup | None = None
        self._active_color_index: int = 0
        self._editing_chip_index: int = -1
        self._current_tool_name: str = "hand"
        self._selection_mode: str = "rect"  # "rect" or "lasso"
        self._eraser_mode: str = "object"  # "object" or "pixel"

        # Eraser tool double-click detection
        self._eraser_click_timer: QTimer = QTimer(self)
        self._eraser_click_timer.setSingleShot(True)
        self._eraser_click_timer.setInterval(self.DOUBLE_CLICK_MS)
        self._eraser_click_timer.timeout.connect(self._on_eraser_single_click)
        self._eraser_pending_id: int = -1

        # Selection tool double-click detection
        self._selection_click_timer: QTimer = QTimer(self)
        self._selection_click_timer.setSingleShot(True)
        self._selection_click_timer.setInterval(self.DOUBLE_CLICK_MS)
        self._selection_click_timer.timeout.connect(self._on_selection_single_click)
        self._selection_pending_id: int = -1

        # Shape tool double-click detection
        self._shape_click_timer: QTimer = QTimer(self)
        self._shape_click_timer.setSingleShot(True)
        self._shape_click_timer.setInterval(self.DOUBLE_CLICK_MS)
        self._shape_click_timer.timeout.connect(self._on_shape_single_click)
        self._shape_pending_id: int = -1

        # Per-tool style memory: tool_name -> (color_chip_index, width_btn_index)
        self._tool_memory: dict[str, tuple[int, int]] = {
            "pen": (0, 0),
            "highlighter": (7, 1),  # default: yellow (#fdd835), medium width
            "eraser": (0, 1),       # default: black, medium radius
            "text": (0, 0),         # default: black, width ignored
            "shape": (0, 1),        # default: black, medium width
        }

        # Live color palette (mutable copy of defaults)
        self._chip_colors: list[str] = list(self.DEFAULT_COLORS)

        # Double-click detection
        self._last_click_chip: int = -1
        self._click_timer: QTimer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(self.DOUBLE_CLICK_MS)
        self._click_timer.timeout.connect(self._on_single_click_confirmed)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 6, 12, 6)
        main_layout.setSpacing(4)

        # --- Undo / Redo buttons ---
        self._undo_btn = QToolButton()
        self._undo_btn.setIcon(IconFactory.create("undo", color="#cccccc"))
        self._undo_btn.setToolTip("Rückgängig (Ctrl+Z)")
        self._undo_btn.setObjectName("undoBtn")
        self._undo_btn.setFixedSize(36, 36)
        self._undo_btn.setIconSize(QSize(20, 20))
        self._undo_btn.setEnabled(False)
        self._undo_btn.setProperty("class", "undo-redo")
        self._undo_btn.clicked.connect(lambda: undo_stack.undo())
        main_layout.addWidget(self._undo_btn)

        self._redo_btn = QToolButton()
        self._redo_btn.setIcon(IconFactory.create("redo", color="#cccccc"))
        self._redo_btn.setToolTip("Wiederholen (Ctrl+Y)")
        self._redo_btn.setObjectName("redoBtn")
        self._redo_btn.setFixedSize(36, 36)
        self._redo_btn.setIconSize(QSize(20, 20))
        self._redo_btn.setEnabled(False)
        self._redo_btn.setProperty("class", "undo-redo")
        self._redo_btn.clicked.connect(lambda: undo_stack.redo())
        main_layout.addWidget(self._redo_btn)

        # Auto-enable/disable via QUndoStack signals
        stack = undo_stack.get_stack()
        stack.canUndoChanged.connect(self._undo_btn.setEnabled)
        stack.canRedoChanged.connect(self._redo_btn.setEnabled)
        stack.undoTextChanged.connect(self._update_undo_tooltip)
        stack.redoTextChanged.connect(self._update_redo_tooltip)

        # Spacer left
        main_layout.addStretch(1)

        # --- Tool buttons ---
        self._tool_group = QButtonGroup(self)
        self._tool_group.setExclusive(True)
        self._tool_buttons: list[QToolButton] = []

        for i, (tool_id, tooltip) in enumerate(
            zip(self.TOOL_IDS, self.TOOL_TOOLTIPS)
        ):
            btn = QToolButton()
            btn.setIcon(IconFactory.create(tool_id))
            btn.setIconSize(QSize(22, 22))
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setObjectName(f"toolBtn_{tool_id}")
            btn.setFixedSize(36, 36)

            if tool_id in self.ENABLED_TOOLS:
                btn.setEnabled(True)
                if tool_id == "hand":
                    btn.setChecked(True)
            else:
                btn.setEnabled(False)

            self._tool_group.addButton(btn, i)
            self._tool_buttons.append(btn)
            main_layout.addWidget(btn)

        self._tool_group.idClicked.connect(self._on_tool_button_clicked)

        # --- Shape dropdown button ---
        from core.shape_style import ShapeType
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction

        self._shape_btn = QToolButton()
        self._shape_btn.setObjectName("shapeToolBtn")
        self._shape_btn.setCheckable(True)
        self._shape_btn.setFixedSize(36, 36)
        self._shape_btn.setIcon(IconFactory.create("shape_rect"))
        self._shape_btn.setIconSize(QSize(22, 22))
        self._shape_btn.setToolTip("Formen\nDoppelklick: Form wählen")

        self._shape_menu = QMenu(self)
        self._shape_menu.setObjectName("shapeMenu")

        _SHAPE_ICON_MAP = {
            ShapeType.RECT: "shape_rect",
            ShapeType.ROUNDED_RECT: "shape_rounded_rect",
            ShapeType.ELLIPSE: "shape_ellipse",
            ShapeType.LINE: "shape_line",
            ShapeType.ARROW: "shape_arrow",
            ShapeType.TRIANGLE: "shape_triangle",
        }
        self._shape_icon_map = _SHAPE_ICON_MAP

        shape_entries = [
            ("Rechteck",          ShapeType.RECT),
            ("Abgerundetes Rect", ShapeType.ROUNDED_RECT),
            ("Ellipse / Kreis",   ShapeType.ELLIPSE),
            ("Linie",             ShapeType.LINE),
            ("Pfeil",             ShapeType.ARROW),
            ("Dreieck",           ShapeType.TRIANGLE),
        ]

        for label, shape_type in shape_entries:
            icon_name = _SHAPE_ICON_MAP[shape_type]
            action = QAction(
                IconFactory.create(icon_name), label, self)
            action.triggered.connect(
                lambda checked, st=shape_type:
                    self._on_shape_selected(st))
            self._shape_menu.addAction(action)

        # Removed setMenu and _on_shape_btn_clicked overrides.

        # Add shape button to tool button group
        shape_idx = len(self._tool_buttons)
        self._tool_group.addButton(self._shape_btn, shape_idx)
        self._tool_buttons.append(self._shape_btn)
        main_layout.addWidget(self._shape_btn)

        # Separator: tools | colors
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setObjectName("toolbarSeparator")
        sep1.setFixedHeight(28)
        main_layout.addWidget(sep1)

        # --- 10 Color chips (single-click = select, double-click = edit) ---
        self._color_group = QButtonGroup(self)
        self._color_group.setExclusive(True)
        self._color_buttons: list[QToolButton] = []

        for i, color in enumerate(self._chip_colors):
            btn = QToolButton()
            btn.setIcon(make_color_icon(color))
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(28, 28)
            btn.setCheckable(True)
            btn.setObjectName("colorChip")
            btn.setToolTip(f"{color}\nDoppelklick zum Anpassen")
            self._color_group.addButton(btn, i)
            self._color_buttons.append(btn)
            main_layout.addWidget(btn)

        self._color_group.idClicked.connect(self._on_chip_raw_click)

        # Select first chip
        if self._color_buttons:
            self._color_buttons[0].setChecked(True)
            self._active_color_index = 0
            self._update_chip_icons()

        # Separator: colors | widths
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setObjectName("toolbarSeparator")
        sep2.setFixedHeight(28)
        main_layout.addWidget(sep2)

        # --- Pen width buttons (5 levels) ---
        self._width_group = QButtonGroup(self)
        self._width_group.setExclusive(True)
        self._width_buttons: list[QToolButton] = []

        for i, (width, dot_r) in enumerate(zip(self.PEN_WIDTHS, self.WIDTH_DOT_RADII)):
            btn = QToolButton()
            btn.setIcon(make_width_icon(dot_r))
            btn.setIconSize(QSize(20, 20))
            btn.setFixedSize(28, 28)
            btn.setCheckable(True)
            btn.setObjectName("widthBtn")
            btn.setToolTip(f"{width:.0f}px")
            if i == 0:
                btn.setChecked(True)
            self._width_group.addButton(btn, i)
            self._width_buttons.append(btn)
            main_layout.addWidget(btn)

        self._width_group.idClicked.connect(self._on_width_clicked)

        # Spacer right
        main_layout.addStretch(1)

        self.setFixedHeight(52)
        
        # Clear/update chips safely for current tool state
        self.update_width_buttons(self._current_tool_name)

    # ------------------------------------------------------------------
    # Undo / Redo tooltip slots
    # ------------------------------------------------------------------

    def _update_undo_tooltip(self, text: str) -> None:
        """Update undo tooltip safely (avoids lambda teardown crash)."""
        self._undo_btn.setToolTip(f"Rückgängig: {text} (Ctrl+Z)" if text else "Rückgängig (Ctrl+Z)")

    def _update_redo_tooltip(self, text: str) -> None:
        """Update redo tooltip safely (avoids lambda teardown crash)."""
        self._redo_btn.setToolTip(f"Wiederholen: {text} (Ctrl+Y)" if text else "Wiederholen (Ctrl+Y)")

    # ------------------------------------------------------------------
    # Double-click detection for color chips
    # ------------------------------------------------------------------

    def _on_chip_raw_click(self, chip_id: int) -> None:
        """Handle raw chip click — detect single vs double click."""
        if self._current_tool_name not in ("pen", "highlighter", "text", "shape"):
            self._clear_color_selection()
            return
            
        if self._click_timer.isActive() and self._last_click_chip == chip_id:
            # Double-click detected
            self._click_timer.stop()
            self._on_chip_double_clicked(chip_id)
        else:
            # Start single-click timer
            self._last_click_chip = chip_id
            self._click_timer.start()

    def _on_single_click_confirmed(self) -> None:
        """Timer expired — this was a genuine single click."""
        chip_id = self._last_click_chip
        if 0 <= chip_id < len(self._chip_colors):
            self._active_color_index = chip_id
            self._update_chip_icons()
            color_hex = self._chip_colors[chip_id]
            self._app_state.update_style(color=QColor(color_hex))
            self.style_changed.emit(self._app_state.tool_style)

    def _on_chip_double_clicked(self, chip_id: int) -> None:
        """Double-click on chip — open picker to customize this slot."""
        if 0 <= chip_id < len(self._chip_colors):
            self._editing_chip_index = chip_id
            self._active_color_index = chip_id
            self._update_chip_icons()

            if self._popup is None:
                self._popup = ColorPickerPopup()
                self._popup.color_selected.connect(self._on_picker_color_changed)

            self._popup.set_color(QColor(self._chip_colors[chip_id]))
            btn = self._color_buttons[chip_id]
            global_pos = btn.mapToGlobal(QPoint(0, btn.height() + 4))
            self._popup.show_at(global_pos)

    def _on_picker_color_changed(self, color: QColor) -> None:
        """Color picker emitted a new color — update the chip being edited."""
        idx = self._editing_chip_index
        if 0 <= idx < len(self._chip_colors):
            self._chip_colors[idx] = color.name()
            self._active_color_index = idx
            self._update_chip_icons()
            self._color_buttons[idx].setChecked(True)

            self._app_state.update_style(color=color)
            self.style_changed.emit(self._app_state.tool_style)

    # ------------------------------------------------------------------
    # Chip icon management
    # ------------------------------------------------------------------

    def _update_chip_icons(self) -> None:
        """Refresh all chip icons, showing checkmark on the active one."""
        for i, btn in enumerate(self._color_buttons):
            btn.setIcon(make_color_icon(
                self._chip_colors[i],
                checked=(i == self._active_color_index),
            ))
            btn.setToolTip(
                f"{self._chip_colors[i]}\nDoppelklick zum Anpassen"
            )

    def select_matching_color(self, color: QColor) -> None:
        """Select the chip whose color is closest to *color*.

        Called when the cursor moves in a textbox to sync the toolbar
        to the text color at cursor position.  Does NOT emit style_changed
        to avoid feedback loops.
        """
        if not self._color_buttons:
            return
        target = color.name().lower()
        # Exact match first
        for i, c in enumerate(self._chip_colors):
            if c.lower() == target:
                if i != self._active_color_index:
                    self._active_color_index = i
                    self._color_buttons[i].setChecked(True)
                    self._update_chip_icons()
                return
        # No exact match → don't change selection

    # ------------------------------------------------------------------
    # Width / tool slots
    # ------------------------------------------------------------------

    def _save_tool_memory(self) -> None:
        """Save current color and width selection for the current tool."""
        if self._current_tool_name in ("pen", "highlighter", "eraser", "text", "shape"):
            width_id = self._width_group.checkedId()
            if width_id < 0:
                width_id = 0
            self._tool_memory[self._current_tool_name] = (
                self._active_color_index,
                width_id,
            )

    def _restore_tool_memory(self, tool_name: str) -> None:
        """Restore saved color and width selection for the given tool."""
        if tool_name not in self._tool_memory:
            return

        color_idx, width_idx = self._tool_memory[tool_name]

        uses_color = tool_name in ("pen", "highlighter", "text", "shape")
        uses_width = tool_name in ("pen", "highlighter", "eraser", "shape")

        # Restore color chip
        if uses_color and 0 <= color_idx < len(self._chip_colors):
            self._active_color_index = color_idx
            self._color_buttons[color_idx].setChecked(True)
            self._update_chip_icons()
            self._app_state.update_style(color=QColor(self._chip_colors[color_idx]))

        # Restore width button
        if uses_width and 0 <= width_idx < len(self._width_buttons):
            self._width_buttons[width_idx].setChecked(True)
            self._app_state.update_style(width=self._active_widths[width_idx])

        self.style_changed.emit(self._app_state.tool_style)

    def _on_tool_button_clicked(self, button_id: int) -> None:
        # Shape button has its own index beyond TOOL_IDS
        if button_id >= len(self.TOOL_IDS):
            # Shape button clicked via group
            if self._current_tool_name == "shape":
                if (self._shape_click_timer.isActive()
                        and self._shape_pending_id == button_id):
                    self._shape_click_timer.stop()
                    self._show_shape_menu()
                else:
                    self._shape_pending_id = button_id
                    self._shape_click_timer.start()
                return

            self._save_tool_memory()
            self._current_tool_name = "shape"
            self.tool_changed.emit("shape")
            return

        if 0 <= button_id < len(self.TOOL_IDS):
            tool_id = self.TOOL_IDS[button_id]

            # Eraser: double-click toggles mode when already active
            if tool_id == "eraser" and self._current_tool_name == "eraser":
                if (self._eraser_click_timer.isActive()
                        and self._eraser_pending_id == button_id):
                    self._eraser_click_timer.stop()
                    self._show_eraser_mode_popup()
                else:
                    self._eraser_pending_id = button_id
                    self._eraser_click_timer.start()
                return

            # Selection: double-click toggles mode when already active
            if tool_id == "selection" and self._current_tool_name == "selection":
                if (self._selection_click_timer.isActive()
                        and self._selection_pending_id == button_id):
                    self._selection_click_timer.stop()
                    self._show_selection_mode_popup()
                else:
                    self._selection_pending_id = button_id
                    self._selection_click_timer.start()
                return

            # Normal tool switch
            self._save_tool_memory()
            self._current_tool_name = tool_id
            self.tool_changed.emit(tool_id)

    def _show_shape_menu(self) -> None:
        pos = self._shape_btn.mapToGlobal(self._shape_btn.rect().bottomLeft())
        self._shape_menu.exec(pos)

    def _on_shape_single_click(self) -> None:
        pass

    def _on_shape_selected(self, shape_type) -> None:
        """Shape menu item selected — update icon + activate tool."""
        from app.app_state import AppState
        AppState().active_shape_type = shape_type
        icon_name = self._shape_icon_map.get(shape_type, "shape_rect")
        self._shape_btn.setIcon(IconFactory.create(icon_name))
        self._shape_btn.setChecked(True)
        self._save_tool_memory()
        self._current_tool_name = "shape"
        self.tool_changed.emit("shape")

    def _clear_color_selection(self) -> None:
        """Visually uncheck all color chips without triggering exclusivity."""
        self._color_group.setExclusive(False)
        for btn in self._color_buttons:
            btn.setChecked(False)
        self._color_group.setExclusive(True)
        self._active_color_index = -1
        self._update_chip_icons()

    def _clear_width_selection(self) -> None:
        """Visually uncheck all width buttons without triggering exclusivity."""
        self._width_group.setExclusive(False)
        for btn in self._width_buttons:
            btn.setChecked(False)
        self._width_group.setExclusive(True)

    def _on_width_clicked(self, width_id: int) -> None:
        if self._current_tool_name not in ("pen", "highlighter", "eraser", "shape"):
            self._clear_width_selection()
            return
            
        if 0 <= width_id < len(self._active_widths):
            self._app_state.update_style(width=self._active_widths[width_id])
            self.style_changed.emit(self._app_state.tool_style)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_active_tool(self, tool_id: str) -> None:
        """Programmatically set the active tool button."""
        for i, tid in enumerate(self.TOOL_IDS):
            if tid == tool_id and i < len(self._tool_buttons):
                self._tool_buttons[i].setChecked(True)
                self._current_tool_name = tool_id
                break

    def set_active_color(self, color: QColor) -> None:
        """Highlight the matching chip, or select the first one."""
        color_hex = color.name().lower()
        for i, chip_hex in enumerate(self._chip_colors):
            if chip_hex.lower() == color_hex:
                self._active_color_index = i
                self._color_buttons[i].setChecked(True)
                self._update_chip_icons()
                return

        # No match — keep current selection
        self._update_chip_icons()

    def update_width_buttons(self, tool_name: str) -> None:
        """Swap width value mapping and restore saved selections.

        Args:
            tool_name: 'pen', 'highlighter', 'eraser', 'text', 'hand', 'selection'.
        """
        uses_color = tool_name in ("pen", "highlighter", "text", "shape")
        uses_width = tool_name in ("pen", "highlighter", "eraser", "shape")

        if tool_name == "highlighter":
            self._active_widths = self.HIGHLIGHTER_WIDTHS
        elif tool_name == "eraser":
            self._active_widths = self.ERASER_WIDTHS
        else:
            self._active_widths = self.PEN_WIDTHS

        # Update eraser tooltip and color chip state
        if tool_name == "eraser":
            self._update_eraser_tooltip()
            
        if not uses_color:
            self._clear_color_selection()
        if not uses_width:
            self._clear_width_selection()

        # Restore saved color + width for this tool
        self._restore_tool_memory(tool_name)
