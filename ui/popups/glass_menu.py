"""Glassmorphic custom QMenu supporting native translucency and pop-in animations."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu
from ui.animations.pop_in import PopInAnimation


class GlassMenu(QMenu):
    """Subclass of QMenu with built-in translucency and pop-in animations.
    
    This matches the premium visual aesthetics of the FormattingBar.
    """
    def __init__(self, title: str | QWidget = "", parent: QWidget | None = None) -> None:
        # Support QMenu(parent=None) and QMenu(title, parent=None) constructors
        if isinstance(title, str):
            super().__init__(title, parent)
        else:
            # title is actually the parent widget
            super().__init__(title)
            
        # Enable translucent background rendering in Qt
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        # Disable native Windows window borders and drop shadows to prevent ugly black corners
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        
    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Play the gorgeous pop-in micro-animation!
        PopInAnimation(self).start()
