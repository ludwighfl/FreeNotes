"""Base tool – abstract interface for all drawing/interaction tools."""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QGraphicsSceneMouseEvent

from app.app_state import AppState
from core.tool_style import ToolStyle

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class BaseTool(QObject):
    """Abstract base class for all tools (Hand, Pen, Highlighter, etc.).

    Subclasses must implement on_press, on_move, and on_release.
    The tool reads its current style from AppState.tool_style.
    """

    tool_action_completed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app_state: AppState = AppState()

    @property
    def style(self) -> ToolStyle:
        """Current tool style from application state."""
        return self._app_state.tool_style

    @property
    def cursor(self) -> Qt.CursorShape:
        """The cursor shape associated with this tool."""
        return Qt.CursorShape.ArrowCursor

    @abstractmethod
    def on_press(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Handle mouse press in the scene.

        Args:
            event: The mouse press event in scene coordinates.
            scene: The PageScene instance.
        """
        ...

    @abstractmethod
    def on_move(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Handle mouse move in the scene.

        Args:
            event: The mouse move event in scene coordinates.
            scene: The PageScene instance.
        """
        ...

    @abstractmethod
    def on_release(self, event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
        """Handle mouse release in the scene.

        Args:
            event: The mouse release event in scene coordinates.
            scene: The PageScene instance.
        """
        ...

    def activate(self, scene: PageScene) -> None:
        """Called when this tool becomes the active tool.

        Override to set cursors or prepare the scene.

        Args:
            scene: The PageScene instance.
        """
        pass

    def deactivate(self, scene: PageScene) -> None:
        """Called when this tool is deactivated.

        Override to clean up state.

        Args:
            scene: The PageScene instance.
        """
        pass
