"""Mixin for ToolbarWidget to manage pen widths and tool style memory."""

from __future__ import annotations

from PySide6.QtGui import QColor

# TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ui.bars.toolbar_widget import ToolbarWidget


class ToolbarWidthMixin:
    """Handles pen width buttons, tool memory preservation, and tool-specific width swapping."""

    def _save_tool_memory(self: 'ToolbarWidget') -> None:
        """Save current color and width selection for the current tool."""
        if self._current_tool_name in ("pen", "highlighter", "eraser", "text", "shape"):
            width_id = self._width_group.checkedId()
            if width_id < 0:
                width_id = 0
            self._tool_memory[self._current_tool_name] = (
                self._active_color_index,
                width_id,
            )
            from core.app_settings import AppSettings
            AppSettings.set_tool_memory(self._tool_memory)

    def _restore_tool_memory(self: 'ToolbarWidget', tool_name: str) -> None:
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

    def _clear_width_selection(self: 'ToolbarWidget') -> None:
        """Visually uncheck all width buttons without triggering exclusivity."""
        self._width_group.setExclusive(False)
        for btn in self._width_buttons:
            btn.setChecked(False)
        self._width_group.setExclusive(True)

    def _on_width_clicked(self: 'ToolbarWidget', width_id: int) -> None:
        if 0 <= width_id < len(self._active_widths):
            self._app_state.update_style(width=self._active_widths[width_id])
            self.style_changed.emit(self._app_state.tool_style)

    def update_width_buttons(self: 'ToolbarWidget', tool_name: str) -> None:
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

        # Enable/disable color and width buttons depending on tool capability
        for btn in self._color_buttons:
            btn.setEnabled(uses_color)
        for btn in self._width_buttons:
            btn.setEnabled(uses_width)

        # Update tooltips for width buttons to reflect the new mapped values
        for i, btn in enumerate(self._width_buttons):
            btn.setToolTip(f"{self._active_widths[i]:.0f}px")

        if uses_color or uses_width:
            self._restore_tool_memory(tool_name)
        else:
            # Hand and selection tools have no color/width settings
            self._clear_color_selection()
            self._clear_width_selection()
