"""Three-dot menu button – file operations (Save, Save As, Export)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QToolButton, QMenu
from PySide6.QtGui import QAction
from core.i18n import tr


class ThreeDotMenu(QToolButton):
    """Three-dot menu button for file operations.

    Provides Save, Save As, Export PDF, Export PDF As actions.
    """
    load_requested = Signal()
    export_requested = Signal()
    export_as_requested = Signal()
    clear_annotations_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("threeDotBtn")
        self.setText("⋯")
        self.setFixedSize(36, 36)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolTip(tr("menu.tooltip"))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._menu = QMenu(self)
        self._menu.setObjectName("threeDotMenu")

        # Actions
        self._action_load = QAction(tr("menu.open"), self)
        self._action_load.setShortcut("Ctrl+O")
        self._action_export = QAction(tr("menu.export_pdf"), self)
        self._action_export_as = QAction(tr("menu.export_pdf_as"), self)
        
        self._action_clear = QAction(tr("menu.clear_annotations"), self)
        # Assuming there is a way to style the action red, or we just rely on the warning dialog
        
        self._menu.addAction(self._action_load)
        self._menu.addSeparator()
        self._menu.addAction(self._action_export)
        self._menu.addAction(self._action_export_as)
        self._menu.addSeparator()
        self._menu.addAction(self._action_clear)

        self.setMenu(self._menu)

        # Connect signals
        self._action_load.triggered.connect(self.load_requested)
        self._action_export.triggered.connect(self.export_requested)
        self._action_export_as.triggered.connect(self.export_as_requested)
        self._action_clear.triggered.connect(self.clear_annotations_requested)
