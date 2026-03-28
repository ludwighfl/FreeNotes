"""Central animation module for FreeNotes UI transitions."""

from ui.animations.fade import (
    FadeAnimation,
    CrossfadeAnimation,
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

__all__ = [
    "FadeAnimation",
    "CrossfadeAnimation",
    "StaggerFadeAnimation",
    "ShadowHoverAnimation",
    "SlideDownAnimation",
]
