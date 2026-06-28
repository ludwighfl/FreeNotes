"""Mixin for ToolbarWidget to manage color chips and color picker popup."""

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QToolButton

from core.i18n import tr
from ui.popups.color_picker_popup import ColorPickerPopup

# TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ui.bars.toolbar_widget import ToolbarWidget


class ToolbarColorMixin:
    """Handles color chip interaction, double clicks, and custom color picker integration."""

    def _on_chip_raw_click(self: 'ToolbarWidget', chip_id: int) -> None:
        """Handle raw chip click — detect single vs double click."""
        if self._click_timer.isActive() and self._last_click_chip == chip_id:
            # Double-click detected
            self._click_timer.stop()
            self._on_chip_double_clicked(chip_id)
        else:
            # Start single-click timer
            self._last_click_chip = chip_id
            self._click_timer.start()

    def _on_single_click_confirmed(self: 'ToolbarWidget') -> None:
        """Timer expired — this was a genuine single click."""
        chip_id = self._last_click_chip
        if 0 <= chip_id < len(self._chip_colors):
            self._active_color_index = chip_id
            self._update_chip_icons()
            color_hex = self._chip_colors[chip_id]
            self._app_state.update_style(color=QColor(color_hex))
            self.style_changed.emit(self._app_state.tool_style)

    def _on_chip_double_clicked(self: 'ToolbarWidget', chip_id: int) -> None:
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

    def _on_picker_color_changed(self: 'ToolbarWidget', color: QColor) -> None:
        """Color picker emitted a new color — update the chip being edited."""
        idx = self._editing_chip_index
        if 0 <= idx < len(self._chip_colors):
            self._chip_colors[idx] = color.name()
            self._active_color_index = idx
            self._update_chip_icons()
            self._color_buttons[idx].setChecked(True)

            self._app_state.update_style(color=color)
            self.style_changed.emit(self._app_state.tool_style)
            
            from core.app_settings import AppSettings
            AppSettings.set_pen_colors(self._chip_colors)

    def _update_chip_icons(self: 'ToolbarWidget') -> None:
        """Refresh all chip icons, showing checkmark on the active one."""
        for i, btn in enumerate(self._color_buttons):
            btn.color_hex = self._chip_colors[i]
            btn.setToolTip(
                tr("toolbar.color_hint").format(self._chip_colors[i])
            )
            btn.update()

    def select_matching_color(self: 'ToolbarWidget', color: QColor) -> None:
        """Select the chip whose color is closest to *color*."""
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

    def _clear_color_selection(self: 'ToolbarWidget') -> None:
        """Visually uncheck all color chips without triggering exclusivity."""
        self._color_group.setExclusive(False)
        for btn in self._color_buttons:
            btn.setChecked(False)
        self._color_group.setExclusive(True)
        self._active_color_index = -1
        self._update_chip_icons()
