"""Toolbar mode popups mixin – eraser and selection mode toggle menus."""

from __future__ import annotations


class ToolbarModePopupsMixin:
    """Mixin providing eraser and selection mode popup menus for ToolbarWidget.

    Expects the host class to provide:
        _eraser_mode: str
        _selection_mode: str
        TOOL_IDS: list[str]
        _tool_buttons: list[QToolButton]
        eraser_mode_changed: Signal(str)
        selection_mode_changed: Signal(str)
    """

    # ------------------------------------------------------------------
    # Eraser mode popup
    # ------------------------------------------------------------------

    def _on_eraser_single_click(self) -> None:
        """Timer expired — was a single click on already-active eraser. No-op."""
        pass

    def _show_eraser_mode_popup(self) -> None:
        """Show a popup menu to choose eraser mode."""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction

        menu = QMenu(self)
        menu.setObjectName("eraserModeMenu")
        menu.setStyleSheet("""
            QMenu#eraserModeMenu {
                background-color: #2d2d2d;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 4px 0;
                font-family: "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QMenu#eraserModeMenu::item {
                padding: 8px 32px 8px 12px;
                color: #cccccc;
            }
            QMenu#eraserModeMenu::item:selected {
                background-color: #3B7BF5;
                color: #ffffff;
            }
            QMenu#eraserModeMenu::separator {
                height: 1px;
                background: #3a3a3a;
                margin: 4px 8px;
            }
        """)

        check = "  ✓  "
        blank = "      "

        obj_action = QAction(
            f"{check if self._eraser_mode == 'object' else blank}Objektradierer",
            menu,
        )
        px_action = QAction(
            f"{check if self._eraser_mode == 'pixel' else blank}Präzisionsradierer",
            menu,
        )

        obj_action.triggered.connect(lambda: self._set_eraser_mode("object"))
        px_action.triggered.connect(lambda: self._set_eraser_mode("pixel"))

        menu.addAction(obj_action)
        menu.addSeparator()
        menu.addAction(px_action)

        # Show below the eraser button
        eraser_idx = self.TOOL_IDS.index("eraser")
        eraser_btn = self._tool_buttons[eraser_idx]
        pos = eraser_btn.mapToGlobal(eraser_btn.rect().bottomLeft())
        menu.exec(pos)

    def _set_eraser_mode(self, mode: str) -> None:
        """Set eraser mode, update tooltip, and persist to settings."""
        self._eraser_mode = mode
        from core.app_settings import AppSettings
        AppSettings.set_eraser_mode(mode)
        self._update_eraser_tooltip()
        self.eraser_mode_changed.emit(mode)

    def _update_eraser_tooltip(self) -> None:
        """Update the eraser button tooltip to show current mode."""
        eraser_idx = self.TOOL_IDS.index("eraser")
        if eraser_idx < len(self._tool_buttons):
            mode_label = "Objektradierer" if self._eraser_mode == "object" else "Präzisionsradierer"
            self._tool_buttons[eraser_idx].setToolTip(
                f"{mode_label}\nDoppelklick: Modus wechseln"
        )

    # ------------------------------------------------------------------
    # Selection mode popup
    # ------------------------------------------------------------------

    def _on_selection_single_click(self) -> None:
        """Timer expired — was a single click on already-active selection. No-op."""
        pass

    def _show_selection_mode_popup(self) -> None:
        """Show a popup menu to choose selection mode."""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction

        menu = QMenu(self)
        menu.setObjectName("selectionModeMenu")
        menu.setStyleSheet("""
            QMenu#selectionModeMenu {
                background-color: #2d2d2d;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
                padding: 4px 0;
                font-family: "Segoe UI", sans-serif;
                font-size: 13px;
            }
            QMenu#selectionModeMenu::item {
                padding: 8px 32px 8px 12px;
                color: #cccccc;
            }
            QMenu#selectionModeMenu::item:selected {
                background-color: #3B7BF5;
                color: #ffffff;
            }
            QMenu#selectionModeMenu::separator {
                height: 1px;
                background: #3a3a3a;
                margin: 4px 8px;
            }
        """)

        check = "  ✓  "
        blank = "      "

        rect_action = QAction(
            f"{check if self._selection_mode == 'rect' else blank}Rechteck-Auswahl",
            menu,
        )
        lasso_action = QAction(
            f"{check if self._selection_mode == 'lasso' else blank}Lasso-Auswahl",
            menu,
        )

        rect_action.triggered.connect(lambda: self._set_selection_mode("rect"))
        lasso_action.triggered.connect(lambda: self._set_selection_mode("lasso"))

        menu.addAction(rect_action)
        menu.addSeparator()
        menu.addAction(lasso_action)

        sel_idx = self.TOOL_IDS.index("selection")
        sel_btn = self._tool_buttons[sel_idx]
        pos = sel_btn.mapToGlobal(sel_btn.rect().bottomLeft())
        menu.exec(pos)

    def _set_selection_mode(self, mode: str) -> None:
        """Set selection mode, update tooltip, and persist to settings."""
        self._selection_mode = mode
        from core.app_settings import AppSettings
        AppSettings.set_selection_mode(mode)
        self._update_selection_tooltip()
        self.selection_mode_changed.emit(mode)

    def _update_selection_tooltip(self) -> None:
        """Update the selection button tooltip to show current mode."""
        sel_idx = self.TOOL_IDS.index("selection")
        if sel_idx < len(self._tool_buttons):
            mode_label = "Rechteck-Auswahl" if self._selection_mode == "rect" else "Lasso-Auswahl"
            self._tool_buttons[sel_idx].setToolTip(
                f"{mode_label}\nDoppelklick: Modus wechseln"
            )
