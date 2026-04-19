"""Viewer tool manager mixin – handles tool switching, styles, and undo creation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core import undo_stack
from commands import AddItemCommand, RemoveItemCommand, ModifyStrokeCommand
from commands.add_textbox_command import AddTextBoxCommand
from tools.pen_tool import PenTool
from tools.highlighter_tool import HighlighterTool
from tools.eraser_tool import EraserTool
from tools.text_tool import TextTool
from tools.shape_tool import ShapeTool

if TYPE_CHECKING:
    from app.app_state import AppState
    from ui.scene.page_scene import PageScene
    from ui.bars.toolbar_widget import ToolbarWidget
    from ui.bars.formatting_bar import FormattingBar
    from items.text_box_item import TextBoxItem
    from tools.hand_tool import HandTool
    from tools.selection_tool import SelectionTool


class ViewerToolManagerMixin:
    """Mixin for ViewerWindow to handle tool, style, and undo operations.

    Expects the host class to provide:
        _app_state: AppState
        _page_scene: PageScene
        _toolbar: ToolbarWidget
        _formatting_bar: FormattingBar
        _hand_tool: HandTool
        _pen_tool: PenTool
        _highlighter_tool: HighlighterTool
        _eraser_tool: EraserTool
        _text_tool: TextTool
        _selection_tool: SelectionTool
        _reposition_formatting_bar(): method
    """

    # ------------------------------------------------------------------
    # Tool & Style Handling
    # ------------------------------------------------------------------

    def _on_tool_changed(self, tool_name: str) -> None:
        """Activate the corresponding tool on the scene."""
        self._app_state.active_tool_name = tool_name

        # When leaving text mode: stop editing + hide bar first
        if tool_name != "text":
            self._page_scene.deselect_all_textboxes()
            self._formatting_bar.hide()
            self._formatting_bar.active_box = None

        if tool_name == "hand":
            self._toolbar.update_width_buttons("hand")
            self._page_scene.set_tool(self._hand_tool)
        elif tool_name == "pen":
            self._app_state.update_style(tool_type="pen")
            self._toolbar.update_width_buttons("pen")
            self._page_scene.set_tool(self._pen_tool)
        elif tool_name == "highlighter":
            self._app_state.update_style(tool_type="highlighter")
            self._toolbar.update_width_buttons("highlighter")
            self._page_scene.set_tool(self._highlighter_tool)
        elif tool_name == "eraser":
            self._app_state.update_style(tool_type="eraser")
            self._toolbar.update_width_buttons("eraser")
            self._eraser_tool.radius = self._app_state.tool_style.width / 2.0
            self._page_scene.set_tool(self._eraser_tool)
        elif tool_name == "text":
            self._app_state.update_style(tool_type="text")
            self._toolbar.update_width_buttons("text")
            self._page_scene.set_tool(self._text_tool)
            self._formatting_bar.show()
            self._reposition_formatting_bar()
            self._connect_all_textbox_signals()
        elif tool_name == "selection":
            self._toolbar.update_width_buttons("selection")
            self._page_scene.set_tool(self._selection_tool)
        elif tool_name == "shape":
            self._toolbar.update_width_buttons("shape")
            self._page_scene.set_tool(self._shape_tool)

    def _on_style_changed(self, style: object) -> None:
        """Style changed from toolbar — route to active tool/item."""
        # If text tool is active, apply color to the editing TextBox
        if self._app_state.active_tool_name == "text":
            active_box = self._get_active_editing_box()
            if active_box is not None and active_box._is_editing:
                active_box.apply_color(self._app_state.tool_style.color)
                return

        if isinstance(self._page_scene.active_tool, EraserTool):
            self._eraser_tool.radius = self._app_state.tool_style.width / 2.0

        # Global selection style update
        from items.stroke_item import StrokeItem
        from items.highlight_item import HighlightItem
        from items.shape_item import ShapeItem
        
        selected_items = self._page_scene.get_selected_items()
        
        stroke_data = [] # (item, old_style, new_style)
        shape_cmds = []
        
        if selected_items:
            for item in selected_items:
                if isinstance(item, (StrokeItem, HighlightItem)):
                    old_style = item.style.copy()
                    new_style = old_style.copy()
                    new_style.color = self._app_state.tool_style.color
                    if isinstance(item, StrokeItem):
                        new_style.width = self._app_state.tool_style.width
                    
                    if old_style.color != new_style.color or old_style.width != new_style.width:
                        stroke_data.append((item, old_style, new_style))
                elif isinstance(item, ShapeItem):
                    from commands.change_shape_style_command import ChangeShapeStyleCommand
                    old_style = item.style.copy()
                    new_style = old_style.copy()
                    new_style.stroke_color = self._app_state.tool_style.color
                    new_style.stroke_width = self._app_state.tool_style.width
                    if old_style.stroke_color != new_style.stroke_color or old_style.stroke_width != new_style.stroke_width:
                        shape_cmds.append(ChangeShapeStyleCommand(item, old_style, new_style, self._page_scene))
            
            if stroke_data or shape_cmds:
                undo_stack.get_stack().beginMacro("Stil ändern")
                if stroke_data:
                    from commands.change_stroke_style_command import ChangeStrokeStyleCommand
                    undo_stack.push(ChangeStrokeStyleCommand(stroke_data, self._page_scene))
                for cmd in shape_cmds:
                    undo_stack.push(cmd)
                undo_stack.get_stack().endMacro()

    def _on_eraser_mode_changed(self, mode_str: str) -> None:
        """Toggle eraser mode between object and pixel."""
        self._eraser_tool.mode = EraserTool.EraserMode(mode_str)

    def _on_tool_switch_requested(self, tool_name: str) -> None:
        """Handle tool switch request from page_scene (e.g. clicking TextBox with hand tool)."""
        self._on_tool_changed(tool_name)
        self._toolbar.set_active_tool(tool_name)

    # ------------------------------------------------------------------
    # Undo stack integration
    # ------------------------------------------------------------------

    def _on_action_completed(self) -> None:
        """Create the appropriate undo command after a tool action completes."""
        tool = self._page_scene.active_tool
        if tool is None:
            return

        if isinstance(tool, (PenTool, HighlighterTool)):
            item = getattr(tool, "last_completed_item", None)
            if item is not None:
                cmd = AddItemCommand(item, self._page_scene)
                undo_stack.push(cmd)

        elif isinstance(tool, EraserTool):
            data = tool.get_last_action_data()
            if tool.mode == EraserTool.EraserMode.OBJECT:
                if not data:
                    return
                # Object eraser: all items fully deleted
                items = [item for item, _ in data]
                cmd = RemoveItemCommand(items, self._page_scene)
                undo_stack.push(cmd)
            else:
                # Pixel eraser: pass affected, deleted, and created items
                deleted = tool._deleted_items
                created = tool.get_created_items()
                shapes_deleted = [it for it, _ in tool._affected_items]

                if not data and not deleted and not created and not shapes_deleted:
                    return

                if shapes_deleted and (data or deleted or created):
                    undo_stack.get_stack().beginMacro("Erase")
                
                if shapes_deleted:
                    undo_stack.push(RemoveItemCommand(shapes_deleted, self._page_scene))

                if data or deleted or created:
                    cmd = ModifyStrokeCommand(
                        data, deleted, created, self._page_scene
                    )
                    undo_stack.push(cmd)

                if shapes_deleted and (data or deleted or created):
                    undo_stack.get_stack().endMacro()

        elif isinstance(tool, TextTool):
            item = tool.last_completed_item
            if item is not None:
                cmd = AddTextBoxCommand(item, self._page_scene)
                undo_stack.push(cmd)
                self._connect_textbox_signals(item)
                self._formatting_bar.active_box = item

    # ------------------------------------------------------------------
    # TextBox ↔ FormattingBar signal management
    # ------------------------------------------------------------------

    def _connect_textbox_signals(self, box: TextBoxItem) -> None:
        """Connect a single TextBoxItem's editing_started to our handler."""
        if not hasattr(self, '_connected_boxes'):
            self._connected_boxes: set = set()
        box_id = id(box)
        if box_id in self._connected_boxes:
            return  # already connected
        self._connected_boxes.add(box_id)
        box.editing_started.connect(
            lambda b=box: self._on_textbox_editing(b))

    def _connect_all_textbox_signals(self) -> None:
        """Connect editing_started on ALL registered TextBoxItems."""
        for page_items in self._page_scene._text_box_items.values():
            for box in page_items:
                self._connect_textbox_signals(box)

    def _on_textbox_editing(self, box: TextBoxItem) -> None:
        """A TextBoxItem started editing — set it as the formatting bar's box."""
        self._formatting_bar.active_box = box

    def _get_active_editing_box(self) -> TextBoxItem | None:
        """Find the currently editing TextBoxItem, if any."""
        from items import TextBoxItem
        for page_boxes in self._page_scene._text_box_items.values():
            for box in page_boxes:
                if isinstance(box, TextBoxItem) and box._is_editing:
                    return box
        return None
