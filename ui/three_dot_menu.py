"""Three-dot menu button – file operations (Save, Save As, Export)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QToolButton, QMenu
from PySide6.QtGui import QAction


class ThreeDotMenu(QToolButton):
    """Three-dot menu button for file operations.

    Provides Save, Save As, Export PDF, Export PDF As actions.
    """

    save_requested = Signal()
    save_as_requested = Signal()
    load_requested = Signal()
    export_requested = Signal()
    export_as_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("threeDotBtn")
        self.setText("⋯")
        self.setFixedSize(36, 36)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolTip("Menü")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._menu = QMenu(self)
        self._menu.setObjectName("threeDotMenu")

        # Actions
        self._action_load = QAction("Öffnen …", self)
        self._action_load.setShortcut("Ctrl+O")
        self._action_save = QAction("Speichern", self)
        self._action_save.setShortcut("Ctrl+S")
        self._action_save_as = QAction("Speichern unter …", self)
        self._action_save_as.setShortcut("Ctrl+Shift+S")
        self._action_export = QAction("Als PDF exportieren", self)
        self._action_export_as = QAction("PDF exportieren als …", self)

        self._menu.addAction(self._action_load)
        self._menu.addSeparator()
        self._menu.addAction(self._action_save)
        self._menu.addAction(self._action_save_as)
        self._menu.addSeparator()
        self._menu.addAction(self._action_export)
        self._menu.addAction(self._action_export_as)

        self.setMenu(self._menu)

        # Connect signals
        self._action_load.triggered.connect(self.load_requested)
        self._action_save.triggered.connect(self.save_requested)
        self._action_save_as.triggered.connect(self.save_as_requested)
        self._action_export.triggered.connect(self.export_requested)
        self._action_export_as.triggered.connect(self.export_as_requested)

    def set_save_enabled(self, enabled: bool) -> None:
        """Enable/disable the 'Save' action (disabled when no file path known)."""
        self._action_save.setEnabled(enabled)
