"""Kinetic scrolling (inertia) for QGraphicsView."""

from __future__ import annotations

import time
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QGraphicsView


class KineticScroller(QObject):
    """Adds inertia/kinetic scrolling to a QGraphicsView after panning."""

    def __init__(self, view: QGraphicsView, parent: QObject | None = None) -> None:
        super().__init__(parent or view)
        self._view = view
        
        self._last_time = 0.0
        self._last_x = 0
        self._last_y = 0
        self._vx = 0.0
        self._vy = 0.0
        
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16) # ~60fps
        self._anim_timer.timeout.connect(self._on_animate)
        
        self._friction = 0.90  # Multiplier per frame (lower = stops faster)

    def on_mouse_press(self, x: int, y: int) -> None:
        """Call on pan start."""
        self._anim_timer.stop()
        self._vx = 0.0
        self._vy = 0.0
        self._last_x = x
        self._last_y = y
        self._last_time = time.time()

    def on_mouse_move(self, x: int, y: int) -> None:
        """Call during pan to update velocity."""
        now = time.time()
        dt = now - self._last_time
        if dt > 0:
            # Velocity in pixels per second
            self._vx = (x - self._last_x) / dt
            self._vy = (y - self._last_y) / dt
            
        self._last_x = x
        self._last_y = y
        self._last_time = now

    def on_mouse_release(self) -> None:
        """Call on pan end to start inertia if velocity is high enough."""
        # Start animation if velocity is significant (> 100 px/sec)
        if abs(self._vx) > 100 or abs(self._vy) > 100:
            # Scale down initial velocity so it's not crazy fast per frame
            self._vx *= 0.016
            self._vy *= 0.016
            self._anim_timer.start()

    def _on_animate(self) -> None:
        if abs(self._vx) < 0.5 and abs(self._vy) < 0.5:
            self._anim_timer.stop()
            return
            
        h_bar = self._view.horizontalScrollBar()
        v_bar = self._view.verticalScrollBar()
        
        # Apply velocity (subtracting because moving mouse left means scrolling right)
        h_bar.setValue(h_bar.value() - int(self._vx))
        v_bar.setValue(v_bar.value() - int(self._vy))
        
        # Apply friction
        self._vx *= self._friction
        self._vy *= self._friction
