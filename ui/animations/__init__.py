"""Central animation module for FreeNotes UI transitions."""

from ui.animations.fade import (
    FadeAnimation,
    StackFadeTransition,
)
from ui.animations.stagger import (
    StaggerFadeAnimation,
)
from ui.animations.slide import (
    SlideDownAnimation,
)
from ui.animations.thumbnail import (
    ThumbnailFadeAnimation,
)
from ui.animations.drag_reorder import (
    DragReorderController,
)
from ui.animations.fade_hover import (
    BackgroundFadeHoverEffect,
)

__all__ = [
    "FadeAnimation",
    "StackFadeTransition",
    "StaggerFadeAnimation",
    "SlideDownAnimation",
    "ThumbnailFadeAnimation",
    "DragReorderController",
    "BackgroundFadeHoverEffect",
]

