"""Central animation module for FreeNotes UI transitions."""

from ui.animations.fade import (
    FadeAnimation,
    StackFadeTransition,
)
from ui.animations.stagger import (
    StaggerFadeAnimation,
)
from ui.animations.shadow import (
    ShadowHoverAnimation,
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

__all__ = [
    "FadeAnimation",
    "StackFadeTransition",
    "StaggerFadeAnimation",
    "ShadowHoverAnimation",
    "SlideDownAnimation",
    "ThumbnailFadeAnimation",
    "DragReorderController",
]
