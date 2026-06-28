"""Mixin for PageView handling touch gestures, tablet/stylus inputs, and mouse panning."""

from __future__ import annotations

import math
from PySide6.QtCore import Qt, QPointF, QEvent, QTimer
from PySide6.QtGui import QTabletEvent
from PySide6.QtWidgets import QGraphicsSceneMouseEvent, QGraphicsView

# TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ui.scene.page_view import PageView


class PageViewGestureMixin:
    """Handles gesture, touch, tablet, key-triggered pan, and mouse panning events."""

    def keyPressEvent(self: 'PageView', event) -> None:
        """Track Space key for pan mode (unless a TextBox is being edited)."""
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if self._is_textbox_editing():
                super(QGraphicsView, self).keyPressEvent(event)
                return
            self._space_pressed = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            super(QGraphicsView, self).keyPressEvent(event)

    def keyReleaseEvent(self: 'PageView', event) -> None:
        """Release Space key pan mode."""
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if self._is_textbox_editing():
                super(QGraphicsView, self).keyReleaseEvent(event)
                return
            self._space_pressed = False
            if not self._panning:
                self._restore_tool_cursor()
        else:
            super(QGraphicsView, self).keyReleaseEvent(event)

    def _is_textbox_editing(self: 'PageView') -> bool:
        """Check if any TextBoxItem in the scene is currently being edited."""
        from items.text_box_item import TextBoxItem
        focus_item = self._page_scene.focusItem()
        return isinstance(focus_item, TextBoxItem) and focus_item._is_editing

    def viewportEvent(self: 'PageView', event: QEvent) -> bool:
        if event.type() == QEvent.Type.TouchBegin:
            if len(event.points()) >= 2:
                self._gesture_active = True
                if self._touch_active:
                    self._touch_active = False
                    touch_point = event.points()[0]
                    scene_pos = self.mapToScene(touch_point.position().toPoint())
                    mouse_event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
                    mouse_event.setButton(Qt.MouseButton.LeftButton)
                    mouse_event.setScenePos(scene_pos)
                    self.scene().mouseReleaseEvent(mouse_event)
                
                p1 = event.points()[0].position()
                p2 = event.points()[1].position()
                self._last_touch_distance = math.hypot(p1.x() - p2.x(), p1.y() - p2.y())
                self._last_touch_center = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                return True

            self._touch_active = True
            touch_point = event.points()[0]
            scene_pos = self.mapToScene(touch_point.position().toPoint())
            
            mouse_event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
            mouse_event.setButton(Qt.MouseButton.LeftButton)
            mouse_event.setButtons(Qt.MouseButton.LeftButton)
            mouse_event.setScenePos(scene_pos)
            self.scene().mousePressEvent(mouse_event)
            return True
            
        elif event.type() == QEvent.Type.TouchUpdate:
            if not self._gesture_active and len(event.points()) >= 2:
                self._gesture_active = True
                if self._touch_active:
                    self._touch_active = False
                    touch_point = event.points()[0]
                    scene_pos = self.mapToScene(touch_point.position().toPoint())
                    mouse_event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
                    mouse_event.setButton(Qt.MouseButton.LeftButton)
                    mouse_event.setScenePos(scene_pos)
                    self.scene().mouseReleaseEvent(mouse_event)
                
                p1 = event.points()[0].position()
                p2 = event.points()[1].position()
                self._last_touch_distance = math.hypot(p1.x() - p2.x(), p1.y() - p2.y())
                self._last_touch_center = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)

            if self._gesture_active:
                if len(event.points()) < 2:
                    self._gesture_active = False
                    return True
                
                p1 = event.points()[0].position()
                p2 = event.points()[1].position()
                new_distance = math.hypot(p1.x() - p2.x(), p1.y() - p2.y())
                new_center = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                
                if self._last_touch_distance > 0:
                    scale_factor = new_distance / self._last_touch_distance
                    new_zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, self._current_zoom * scale_factor))
                    
                    self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
                    self.scale(new_zoom / self._current_zoom, new_zoom / self._current_zoom)
                    self._current_zoom = new_zoom
                    self._target_zoom = new_zoom
                    self._app_state.zoom_factor = new_zoom
                    self._update_mip_for_zoom()
                
                delta = new_center - self._last_touch_center
                h_bar = self.horizontalScrollBar()
                v_bar = self.verticalScrollBar()
                h_bar.setValue(h_bar.value() - int(delta.x()))
                v_bar.setValue(v_bar.value() - int(delta.y()))
                
                self._last_touch_distance = new_distance
                self._last_touch_center = new_center
                return True

            if self._touch_active:
                touch_point = event.points()[0]
                scene_pos = self.mapToScene(touch_point.position().toPoint())
                
                mouse_event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseMove)
                mouse_event.setButtons(Qt.MouseButton.LeftButton)
                mouse_event.setScenePos(scene_pos)
                self.scene().mouseMoveEvent(mouse_event)
                return True
                
        elif event.type() in (QEvent.Type.TouchEnd, QEvent.Type.TouchCancel):
            was_gesture = self._gesture_active
            self._gesture_active = False
            
            if self._touch_active:
                self._touch_active = False
                touch_point = event.points()[0]
                scene_pos = self.mapToScene(touch_point.position().toPoint())
                
                mouse_event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
                mouse_event.setButton(Qt.MouseButton.LeftButton)
                mouse_event.setScenePos(scene_pos)
                self.scene().mouseReleaseEvent(mouse_event)
                
            if was_gesture:
                QTimer.singleShot(200, self._on_render_timer)
                
            return True
            
        return super(QGraphicsView, self).viewportEvent(event)

    def tabletEvent(self: 'PageView', event: QTabletEvent) -> None:
        if self._gesture_active:
            event.accept()
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        
        if event.type() == QEvent.Type.TabletPress:
            self._touch_active = True
            mouse_event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
            mouse_event.setButton(Qt.MouseButton.LeftButton)
            mouse_event.setButtons(Qt.MouseButton.LeftButton)
            mouse_event.setScenePos(scene_pos)
            self.scene().mousePressEvent(mouse_event)
            event.accept()
            
        elif event.type() == QEvent.Type.TabletMove:
            mouse_event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseMove)
            mouse_event.setButtons(Qt.MouseButton.LeftButton)
            mouse_event.setScenePos(scene_pos)
            self.scene().mouseMoveEvent(mouse_event)
            event.accept()
            
        elif event.type() == QEvent.Type.TabletRelease:
            self._touch_active = False
            mouse_event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
            mouse_event.setButton(Qt.MouseButton.LeftButton)
            mouse_event.setScenePos(scene_pos)
            self.scene().mouseReleaseEvent(mouse_event)
            event.accept()
        else:
            super(QGraphicsView, self).tabletEvent(event)

    def mousePressEvent(self: 'PageView', event) -> None:
        """Handle pan (Space+Left / Middle), otherwise forward to scene."""
        if hasattr(event, "source") and event.source() == Qt.MouseEventSource.MouseEventSynthesizedByQt and (self._touch_active or self._gesture_active):
            return

        if (
            self._space_pressed and event.button() == Qt.MouseButton.LeftButton
        ) or event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start_x = event.x()
            self._pan_start_y = event.y()
            self._kinetic_scroller.on_mouse_press(event.x(), event.y())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super(QGraphicsView, self).mousePressEvent(event)

    def mouseMoveEvent(self: 'PageView', event) -> None:
        """Pan or forward to scene."""
        if hasattr(event, "source") and event.source() == Qt.MouseEventSource.MouseEventSynthesizedByQt and (self._touch_active or self._gesture_active):
            return

        if self._panning:
            dx = event.x() - self._pan_start_x
            dy = event.y() - self._pan_start_y
            self._pan_start_x = event.x()
            self._pan_start_y = event.y()
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - dx)
            v_bar.setValue(v_bar.value() - dy)
            self._kinetic_scroller.on_mouse_move(event.x(), event.y())
            event.accept()
        else:
            super(QGraphicsView, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self: 'PageView', event) -> None:
        """Stop panning or forward to scene."""
        if hasattr(event, "source") and event.source() == Qt.MouseEventSource.MouseEventSynthesizedByQt and (self._touch_active or self._gesture_active):
            return

        if self._panning:
            self._panning = False
            self._kinetic_scroller.on_mouse_release()
            if self._space_pressed:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self._restore_tool_cursor()
            event.accept()
        else:
            super(QGraphicsView, self).mouseReleaseEvent(event)

    def _restore_tool_cursor(self: 'PageView') -> None:
        """Restore cursor based on the active tool."""
        tool = self._page_scene.active_tool
        if tool is not None:
            self.viewport().setCursor(tool.cursor)
            self.setCursor(tool.cursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            self.setCursor(Qt.CursorShape.ArrowCursor)
