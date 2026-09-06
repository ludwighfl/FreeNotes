"""Mixin for PageView handling zoom, smooth scroll-to-page, and visible page detection."""

from __future__ import annotations

import gc
import time
from PySide6.QtCore import Qt, QTimer, QPointF, QVariantAnimation
from PySide6.QtWidgets import QGraphicsView

from core.tile_cache import MipLevel

# TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ui.scene.page_view import PageView


class PageViewNavigationMixin:
    """Handles zoom animations, scroll-to-page, and virtual rendering triggers."""

    def wheelEvent(self: 'PageView', event) -> None:
        """Zoom in/out with Ctrl+Scroll (smooth)."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            if angle > 0:
                factor = self.ZOOM_FACTOR
            elif angle < 0:
                factor = 1.0 / self.ZOOM_FACTOR
            else:
                return

            self._target_zoom = max(
                self.ZOOM_MIN, min(self.ZOOM_MAX, self._target_zoom * factor)
            )

            self._zoom_anim.stop()
            self._zoom_anim.setStartValue(self._current_zoom)
            self._zoom_anim.setEndValue(self._target_zoom)
            self._zoom_anim.start()
            event.accept()
        else:
            super().wheelEvent(event)

    def _on_zoom_anim_value_changed(self: 'PageView', value: float) -> None:
        """Apply the intermediate zoom factor during animation."""
        if self._current_zoom == 0:
            return

        factor = value / self._current_zoom
        self.scale(factor, factor)
        self._current_zoom = value

        self._app_state.zoom_factor = value
        self._update_mip_for_zoom()

        if value == self._target_zoom:
            QTimer.singleShot(200, self._on_render_timer)

    def zoom_to_fit(self: 'PageView') -> None:
        """Fit the current page into the viewport."""
        page_index = self._app_state.current_page
        rect = self._page_scene.get_page_rect(page_index)
        if rect.isEmpty():
            return

        self.resetTransform()
        self._current_zoom = 1.0
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

        transform = self.transform()
        self._current_zoom = transform.m11()
        self._target_zoom = self._current_zoom
        self._app_state.zoom_factor = self._current_zoom
        self._update_mip_for_zoom()

    def set_zoom(self: 'PageView', zoom: float) -> None:
        """Set the zoom to a specific level (no animation)."""
        zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, zoom))
        self.resetTransform()
        self.scale(zoom, zoom)
        self._current_zoom = zoom
        self._target_zoom = zoom
        self._app_state.zoom_factor = zoom
        self._update_mip_for_zoom()
        QTimer.singleShot(200, self._on_render_timer)

    def scroll_to_page(self: 'PageView', page_index: int) -> None:
        """Scroll the view so the top of the given page is at the top of the viewport."""
        rect = self._page_scene.get_page_rect(page_index)
        if rect.isEmpty():
            return

        self._app_state.current_page = page_index

        margin = 20
        target_scene_y = rect.top() - margin
        
        vp_height = self.viewport().height()
        scale_y = self.transform().m22()
        scene_vp_half = (vp_height / 2) / scale_y
        
        self._scroll_anim.scroll_to(
            QPointF(rect.center().x(), target_scene_y + scene_vp_half)
        )

    def _on_scroll(self: 'PageView') -> None:
        """Detect which page occupies the most space in the viewport."""
        try:
            viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        except RuntimeError:
            return

        rects = self._page_scene._page_rects
        if not rects:
            return

        best_index = 0
        max_area = -1.0

        offsets = self._page_scene._page_y_offsets
        import bisect
        idx = bisect.bisect_right(offsets, viewport_rect.top())
        start_idx = max(0, idx - 1)
        
        for i in range(start_idx, len(rects)):
            r = rects[i]
            if r.top() > viewport_rect.bottom():
                break
                
            intersect = r.intersected(viewport_rect)
            if not intersect.isEmpty():
                area = intersect.width() * intersect.height()
                if area > max_area:
                    max_area = area
                    best_index = i

        try:
            if max_area >= 0 and best_index != self._app_state.current_page:
                if self._scroll_anim.is_running():
                    return
                self._app_state.current_page = best_index
                self.visible_page_changed.emit(best_index)
        except RuntimeError:
            pass

    def _on_scroll_changed(self: 'PageView') -> None:
        """Start or restart the debounce timer on scroll."""
        if (self._scroll_anim.is_running() or 
            self._zoom_anim.state() == QVariantAnimation.State.Running):
            return

        if hasattr(self, '_upgrade_timer') and self._upgrade_timer.isActive():
            self._upgrade_timer.stop()

        current_time = time.perf_counter()
        current_val = self.verticalScrollBar().value()
        
        if getattr(self, '_last_scroll_time', None) is not None and getattr(self, '_last_scroll_val_velocity', None) is not None:
            dt = current_time - self._last_scroll_time
            dy = abs(current_val - self._last_scroll_val_velocity)
            if dt > 0:
                instant_velocity = dy / dt
                self._scroll_velocity = 0.7 * getattr(self, '_scroll_velocity', 0.0) + 0.3 * instant_velocity
        else:
            self._scroll_velocity = 0.0
            
        self._last_scroll_time = current_time
        self._last_scroll_val_velocity = current_val

        gc.disable()
        self._render_timer.start()

    def _on_render_timer(self: 'PageView') -> None:
        """Inform scene which pages are visible for rendering."""
        gc.enable()
        gc.collect(0)
        
        try:
            vp_rect = self.mapToScene(
                self.viewport().rect()).boundingRect()
            scene = self.scene()
            if scene and hasattr(scene, 'update_visible_pages'):
                current_scroll_y = self.verticalScrollBar().value()
                if not hasattr(self, '_last_scroll_y'):
                    self._last_scroll_y = current_scroll_y
                
                scroll_direction = 0
                if current_scroll_y > self._last_scroll_y:
                    scroll_direction = 1
                elif current_scroll_y < self._last_scroll_y:
                    scroll_direction = -1
                
                self._last_scroll_y = current_scroll_y
                
                if hasattr(self, '_last_scroll_time') and self._last_scroll_time is not None:
                    time_since_scroll = time.perf_counter() - self._last_scroll_time
                    if time_since_scroll > 0.045:
                        self._scroll_velocity = 0.0

                velocity = getattr(self, '_scroll_velocity', 0.0)
                max_mip_level = None
                if velocity > 800:
                    max_mip_level = MipLevel.THUMB
                elif velocity > 200:
                    max_mip_level = MipLevel.MEDIUM

                self._scroll_velocity = 0.0
                self._last_scroll_time = None
                self._last_scroll_val_velocity = None

                scene.update_visible_pages(vp_rect, scroll_direction=scroll_direction, max_mip_override=max_mip_level)
                
                if max_mip_level is not None:
                    if not hasattr(self, '_upgrade_timer'):
                        self._upgrade_timer = QTimer(self)
                        self._upgrade_timer.setSingleShot(True)
                        self._upgrade_timer.timeout.connect(self._on_upgrade_timer)
                    self._upgrade_timer.setInterval(150)
                    self._upgrade_timer.start()
        except RuntimeError:
            pass

    def _on_upgrade_timer(self: 'PageView') -> None:
        """Upgrade visible pages to full resolution after scrolling has fully stopped."""
        try:
            vp_rect = self.mapToScene(
                self.viewport().rect()).boundingRect()
            scene = self.scene()
            if scene and hasattr(scene, 'update_visible_pages'):
                scene.update_visible_pages(vp_rect, scroll_direction=0, max_mip_override=None)
        except RuntimeError:
            pass

    def _update_mip_for_zoom(self: 'PageView') -> None:
        """Set the scene's current mip level based on the zoom factor."""
        if self._current_zoom < 0.6:
            mip = MipLevel.THUMB
        elif self._current_zoom < 1.2:
            mip = MipLevel.MEDIUM
        else:
            mip = MipLevel.FULL
        self._page_scene._current_mip = mip
