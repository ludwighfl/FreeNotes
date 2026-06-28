"""Toolbar widget – tool buttons, 10 customizable color chips, and pen width controls."""

from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QToolButton,
    QFrame,
    QButtonGroup,
)

from app.app_state import AppState
from core import undo_stack
from ui.components.icon_factory import IconFactory
from ui.bars.toolbar_icons import make_width_icon
from ui.bars.toolbar_mode_popups import ToolbarModePopupsMixin
from ui.bars.color_chip_button import ColorChipButton
from ui.bars.toolbar_color_mixin import ToolbarColorMixin
from ui.bars.toolbar_width_mixin import ToolbarWidthMixin
from core.i18n import tr
from core.app_settings import AppSettings


class ToolbarWidget(
    ToolbarModePopupsMixin,
    ToolbarColorMixin,
    ToolbarWidthMixin,
    QWidget
):
    """Horizontal toolbar with Lucide tool icons, 10 customizable color chips,
    and 5 pen width controls.

    Features are modularly split into mixins:
    - ToolbarModePopupsMixin: Handles tool double-click mode selection popups.
    - ToolbarColorMixin: Handles color chips, palette customization, and picker.
    - ToolbarWidthMixin: Handles width buttons and tool style memory.
    """

    tool_changed = Signal(str)
    style_changed = Signal(object)  # ToolStyle
    eraser_mode_changed = Signal(str)  # "object" or "pixel"
    selection_mode_changed = Signal(str)  # "rect" or "lasso"

    TOOL_IDS: list[str] = ["text", "hand", "pen", "highlighter", "eraser", "selection"]
    TOOL_TOOLTIPS: list[str] = [
        "toolbar.text", "toolbar.hand", "toolbar.pen", "toolbar.highlighter", "toolbar.eraser",
        "toolbar.selection",
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
        
        self._current_tool_name: str = AppSettings.get_active_tool()
        self._selection_mode: str = AppSettings.get_selection_mode()
        self._eraser_mode: str = AppSettings.get_eraser_mode()

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
        default_memory = {
            "pen": (0, 0),
            "highlighter": (7, 1),
            "eraser": (0, 1),
            "text": (0, 0),
            "shape": (0, 1),
        }
        loaded_memory = AppSettings.get_tool_memory()
        self._tool_memory: dict[str, tuple[int, int]] = {
            k: tuple(loaded_memory.get(k, default_memory.get(k, (0, 0))))
            for k in default_memory.keys()
        }

        # Live color palette
        self._chip_colors: list[str] = AppSettings.get_pen_colors()

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
        self._undo_btn.setToolTip(tr("toolbar.undo"))
        self._undo_btn.setObjectName("undoBtn")
        self._undo_btn.setFixedSize(36, 36)
        self._undo_btn.setIconSize(QSize(20, 20))
        self._undo_btn.setEnabled(False)
        self._undo_btn.setProperty("class", "undo-redo")
        self._undo_btn.clicked.connect(lambda: undo_stack.undo())
        main_layout.addWidget(self._undo_btn)

        self._redo_btn = QToolButton()
        self._redo_btn.setIcon(IconFactory.create("redo", color="#cccccc"))
        self._redo_btn.setToolTip(tr("toolbar.redo"))
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
            btn.setToolTip(tr(tooltip))
            btn.setCheckable(True)
            btn.setObjectName(f"toolBtn_{tool_id}")
            btn.setFixedSize(36, 36)

            if tool_id in self.ENABLED_TOOLS:
                btn.setEnabled(True)
                if tool_id == self._current_tool_name:
                    btn.setChecked(True)
            else:
                btn.setEnabled(False)

            self._tool_group.addButton(btn, i)
            self._tool_buttons.append(btn)
            main_layout.addWidget(btn)

        self._tool_group.idClicked.connect(self._on_tool_button_clicked)

        # --- Shape dropdown button ---
        from core.shape_style import ShapeType
        from PySide6.QtGui import QAction
        from ui.popups.glass_menu import GlassMenu

        self._shape_btn = QToolButton()
        self._shape_btn.setObjectName("shapeToolBtn")
        self._shape_btn.setCheckable(True)
        self._shape_btn.setFixedSize(36, 36)
        self._shape_btn.setIcon(IconFactory.create("shape_rect"))
        self._shape_btn.setIconSize(QSize(22, 22))
        self._shape_btn.setToolTip(tr("toolbar.shapes_hint"))

        self._shape_menu = GlassMenu(self)
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
            (tr("toolbar.shape_rect"),          ShapeType.RECT),
            (tr("toolbar.shape_rounded_rect"), ShapeType.ROUNDED_RECT),
            (tr("toolbar.shape_ellipse"),   ShapeType.ELLIPSE),
            (tr("toolbar.shape_line"),             ShapeType.LINE),
            (tr("toolbar.shape_arrow"),             ShapeType.ARROW),
            (tr("toolbar.shape_triangle"),           ShapeType.TRIANGLE),
        ]

        self._shape_actions = []
        for label, shape_type in shape_entries:
            icon_name = _SHAPE_ICON_MAP[shape_type]
            action = QAction(
                IconFactory.create(icon_name), label, self)
            action.triggered.connect(
                lambda checked, st=shape_type:
                    self._on_shape_selected(st))
            self._shape_menu.addAction(action)
            self._shape_actions.append((action, shape_type))

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
        sep1.setFixedWidth(1)
        main_layout.addWidget(sep1)

        # --- 10 Color chips (single-click = select, double-click = edit) ---
        self._color_group = QButtonGroup(self)
        self._color_group.setExclusive(True)
        self._color_buttons: list[ColorChipButton] = []

        for i, color in enumerate(self._chip_colors):
            btn = ColorChipButton(color, self)
            btn.setObjectName("colorChip")
            btn.setToolTip(tr("toolbar.color_hint").format(color))
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
        sep2.setFixedWidth(1)
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

        # Install smooth background hover fade animations on primary toolbar buttons
        from ui.animations.fade_hover import BackgroundFadeHoverEffect
        
        hover_color = QColor(0, 0, 0, 18) if AppSettings.get_theme() == "light" else QColor(255, 255, 255, 25)
        
        self._hover_effects = []
        self._hover_effects.append(BackgroundFadeHoverEffect(self._undo_btn, hover_color, duration=150, border_radius=6))
        self._hover_effects.append(BackgroundFadeHoverEffect(self._redo_btn, hover_color, duration=150, border_radius=6))
        
        for btn in self._tool_buttons:
            self._hover_effects.append(BackgroundFadeHoverEffect(btn, hover_color, duration=150, border_radius=6))

        self._app_state.theme_updated.connect(self._on_theme_updated)

    def _on_theme_updated(self) -> None:
        """Dynamically refresh all static SVG icons and hover effect colors on theme switch."""
        hover_color = QColor(0, 0, 0, 18) if AppSettings.get_theme() == "light" else QColor(255, 255, 255, 25)
        
        self._undo_btn.setIcon(IconFactory.create("undo", color="#cccccc"))
        self._redo_btn.setIcon(IconFactory.create("redo", color="#cccccc"))
        
        for i, tool_id in enumerate(self.TOOL_IDS):
            if i < len(self._tool_buttons):
                self._tool_buttons[i].setIcon(IconFactory.create(tool_id))
                
        active_shape = AppState().active_shape_type
        icon_name = self._shape_icon_map.get(active_shape, "shape_rect")
        self._shape_btn.setIcon(IconFactory.create(icon_name))
        
        if hasattr(self, '_shape_actions'):
            for action, st in self._shape_actions:
                action_icon_name = self._shape_icon_map.get(st, "shape_rect")
                action.setIcon(IconFactory.create(action_icon_name))
        
        self._hover_effects.clear()
        from ui.animations.fade_hover import BackgroundFadeHoverEffect
        self._hover_effects.append(BackgroundFadeHoverEffect(self._undo_btn, hover_color, duration=150, border_radius=6))
        self._hover_effects.append(BackgroundFadeHoverEffect(self._redo_btn, hover_color, duration=150, border_radius=6))
        for btn in self._tool_buttons:
            self._hover_effects.append(BackgroundFadeHoverEffect(btn, hover_color, duration=150, border_radius=6))

        if hasattr(self, "_width_buttons"):
            for i, (width, dot_r) in enumerate(zip(self.PEN_WIDTHS, self.WIDTH_DOT_RADII)):
                if i < len(self._width_buttons):
                    self._width_buttons[i].setIcon(make_width_icon(dot_r))

    def showEvent(self, event) -> None:
        """Reload settings from AppSettings when toolbar becomes visible."""
        super().showEvent(event)
        self._chip_colors = list(AppSettings.get_pen_colors())
        self._update_chip_icons()

    def _update_undo_tooltip(self, text: str) -> None:
        """Update undo tooltip safely (avoids lambda teardown crash)."""
        self._undo_btn.setToolTip(tr("toolbar.undo_action").format(text) if text else tr("toolbar.undo"))

    def _update_redo_tooltip(self, text: str) -> None:
        """Update redo tooltip safely (avoids lambda teardown crash)."""
        self._redo_btn.setToolTip(tr("toolbar.redo_action").format(text) if text else tr("toolbar.redo"))

    def _on_tool_button_clicked(self, button_id: int) -> None:
        # Shape button has its own index beyond TOOL_IDS
        if button_id >= len(self.TOOL_IDS):
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
            AppSettings.set_active_tool(tool_id)
            self.tool_changed.emit(tool_id)

    def _show_shape_menu(self) -> None:
        pos = self._shape_btn.mapToGlobal(self._shape_btn.rect().bottomLeft())
        self._shape_menu.exec(pos)

    def _on_shape_single_click(self) -> None:
        pass

    def _on_shape_selected(self, shape_type) -> None:
        """Shape menu item selected — update icon + activate tool."""
        AppState().active_shape_type = shape_type
        icon_name = self._shape_icon_map.get(shape_type, "shape_rect")
        self._shape_btn.setIcon(IconFactory.create(icon_name))
        self._shape_btn.setChecked(True)
        self._save_tool_memory()
        self._current_tool_name = "shape"
        AppSettings.set_active_tool("shape")
        self.tool_changed.emit("shape")

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
        self._update_chip_icons()

    def sync_selection_style(self, colors: set[str], widths: set[float]) -> None:
        """Sync the toolbar state (checked chips/widths) to the current selection's styles."""
        self._color_group.blockSignals(True)
        self._width_group.blockSignals(True)
        
        try:
            # 1. Colors
            if len(colors) == 1:
                color_hex = list(colors)[0].lower()
                matched_idx = -1
                for i, chip_hex in enumerate(self._chip_colors):
                    if chip_hex.lower() == color_hex:
                        matched_idx = i
                        break
                
                if matched_idx != -1:
                    self._active_color_index = matched_idx
                    self._color_buttons[matched_idx].setChecked(True)
                    self._update_chip_icons()
                else:
                    self._clear_color_selection()
                
                self._app_state.update_style(color=QColor(color_hex))
            else:
                self._clear_color_selection()
            
            # 2. Widths
            if len(widths) == 1:
                width_val = list(widths)[0]
                matched_idx = -1
                for i, w in enumerate(self._active_widths):
                    if abs(w - width_val) < 0.01:
                        matched_idx = i
                        break
                
                if matched_idx != -1:
                    self._width_buttons[matched_idx].setChecked(True)
                else:
                    self._clear_width_selection()
                
                self._app_state.update_style(width=width_val)
            else:
                self._clear_width_selection()
                
        finally:
            self._color_group.blockSignals(False)
            self._width_group.blockSignals(False)
