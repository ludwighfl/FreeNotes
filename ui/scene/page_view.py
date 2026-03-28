"""Graphics view for PDF pages – zoom, pan, and scroll-to-page."""

from PySide6.QtCore import (
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsView

from app.app_state import AppState
from ui.page_scene import PageScene


class PageView(QGraphicsView):
    """QGraphicsView with zoom (Ctrl+Scroll), pan (Space+Drag / Middle-mouse),
    and smooth scroll-to-page support.

    When the active tool is NOT HandTool, mouse events are forwarded to the
    scene for tool processing. Space+Drag and Middle-mouse pan always work
    regardless of the active tool.
    """

    ZOOM_FACTOR: float = 1.15
    ZOOM_MIN: float = 0.1
    ZOOM_MAX: float = 5.0

    visible_page_changed = Signal(int)

    def __init__(self, scene: PageScene, parent: object = None) -> None:
        super().__init__(scene, parent)
        self._page_scene: PageScene = scene
        self._app_state: AppState = AppState()
        self._current_zoom: float = 1.0
        self._space_pressed: bool = False
        self._panning: bool = False
        self._pan_start_x: int = 0
        self._pan_start_y: int = 0

        # Render hints
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate
        )
        self.setBackgroundBrush(Qt.GlobalColor.transparent)

        # Track scrolling to detect current visible page
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

        # Debounced render timer for virtual page rendering
        self._render_timer = QTimer()
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(80)
        self._render_timer.timeout.connect(self._on_render_timer)
        self.verticalScrollBar().valueChanged.connect(
            self._on_scroll_changed)
        self.horizontalScrollBar().valueChanged.connect(
            self._on_scroll_changed)

    # ------------------------------------------------------------------
    # Eraser cursor visibility on enter/leave
    # ------------------------------------------------------------------

    def leaveEvent(self, event: object) -> None:
        scene = self.scene()
        if scene is not None and hasattr(scene, "set_eraser_cursor_visible"):
            scene.set_eraser_cursor_visible(False)
        super().leaveEvent(event)

    def enterEvent(self, event: object) -> None:
        scene = self.scene()
        if scene is not None and hasattr(scene, "set_eraser_cursor_visible"):
            scene.set_eraser_cursor_visible(True)
        # Safely restore tool's cursor so it doesn't get lost
        self._restore_tool_cursor()
        super().enterEvent(event)

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def wheelEvent(self, event: object) -> None:
        """Zoom in/out with Ctrl+Scroll."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            if angle > 0:
                factor = self.ZOOM_FACTOR
            elif angle < 0:
                factor = 1.0 / self.ZOOM_FACTOR
            else:
                return

            new_zoom = self._current_zoom * factor
            if new_zoom < self.ZOOM_MIN:
                factor = self.ZOOM_MIN / self._current_zoom
                new_zoom = self.ZOOM_MIN
            elif new_zoom > self.ZOOM_MAX:
                factor = self.ZOOM_MAX / self._current_zoom
                new_zoom = self.ZOOM_MAX

            self._current_zoom = new_zoom
            self.scale(factor, factor)
            self._app_state.zoom_factor = new_zoom
            # Trigger re-render after zoom
            QTimer.singleShot(200, self._on_render_timer)
        else:
            super().wheelEvent(event)

    def zoom_to_fit(self) -> None:
        """Fit the current page into the viewport."""
        page_index = self._app_state.current_page
        rect = self._page_scene.get_page_rect(page_index)
        if rect.isEmpty():
            return

        self.resetTransform()
        self._current_zoom = 1.0
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

        # Recalculate actual zoom factor from transform
        transform = self.transform()
        self._current_zoom = transform.m11()
        self._app_state.zoom_factor = self._current_zoom

    def set_zoom(self, zoom: float) -> None:
        """Set the zoom to a specific level (no animation)."""
        zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, zoom))
        self.resetTransform()
        self.scale(zoom, zoom)
        self._current_zoom = zoom
        self._app_state.zoom_factor = zoom
        # Trigger re-render after zoom
        QTimer.singleShot(200, self._on_render_timer)

    # ------------------------------------------------------------------
    # Pan (Space+Drag / Middle-mouse – always available)
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: object) -> None:
        """Track Space key for pan mode (unless a TextBox is being edited)."""
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            # If a TextBoxItem is being edited, let Space go to the text
            if self._is_textbox_editing():
                super().keyPressEvent(event)
                return
            self._space_pressed = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: object) -> None:
        """Release Space key pan mode."""
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if self._is_textbox_editing():
                super().keyReleaseEvent(event)
                return
            self._space_pressed = False
            if not self._panning:
                self._restore_tool_cursor()
        else:
            super().keyReleaseEvent(event)

    def _is_textbox_editing(self) -> bool:
        """Check if any TextBoxItem in the scene is currently being edited."""
        from items.text_box_item import TextBoxItem
        focus_item = self._page_scene.focusItem()
        return isinstance(focus_item, TextBoxItem) and focus_item._is_editing

    def mousePressEvent(self, event: object) -> None:
        """Handle pan (Space+Left / Middle), otherwise forward to scene."""
        if (
            self._space_pressed and event.button() == Qt.MouseButton.LeftButton
        ) or event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start_x = event.x()
            self._pan_start_y = event.y()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            # Forward to scene for tool processing
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: object) -> None:
        """Pan or forward to scene."""
        if self._panning:
            dx = event.x() - self._pan_start_x
            dy = event.y() - self._pan_start_y
            self._pan_start_x = event.x()
            self._pan_start_y = event.y()
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - dx)
            v_bar.setValue(v_bar.value() - dy)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: object) -> None:
        """Stop panning or forward to scene."""
        if self._panning:
            self._panning = False
            if self._space_pressed:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self._restore_tool_cursor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _restore_tool_cursor(self) -> None:
        """Restore cursor based on the active tool."""
        tool = self._page_scene.active_tool
        if tool is not None:
            # Set cursor directly instead of re-activating the tool
            self.viewport().setCursor(tool.cursor)
            self.setCursor(tool.cursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            self.setCursor(Qt.CursorShape.ArrowCursor)

    # ------------------------------------------------------------------
    # Scroll to page
    # ------------------------------------------------------------------

    def scroll_to_page(self, page_index: int) -> None:
        """Smoothly scroll the view to center the given page.

        Args:
            page_index: Zero-based page index.
        """
        rect = self._page_scene.get_page_rect(page_index)
        if rect.isEmpty():
            return

        # Use ensureVisible with margins for a smooth-ish scroll
        self.ensureVisible(rect, 50, 50)
        self._app_state.current_page = page_index

    # ------------------------------------------------------------------
    # Visible page detection
    # ------------------------------------------------------------------

    def _on_scroll(self) -> None:
        """Detect which page is most visible after scrolling."""
        try:
            viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        except RuntimeError:
            return
        viewport_center_y = viewport_rect.center().y()

        best_index = 0
        best_distance = float("inf")

        for i in range(self._page_scene.page_count):
            page_rect = self._page_scene.get_page_rect(i)
            if page_rect.isEmpty():
                continue
            page_center_y = page_rect.center().y()
            distance = abs(viewport_center_y - page_center_y)
            if distance < best_distance:
                best_distance = distance
                best_index = i

        try:
            if best_index != self._app_state.current_page:
                self._app_state.current_page = best_index
                self.visible_page_changed.emit(best_index)
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Virtual rendering triggers
    # ------------------------------------------------------------------

    def _on_scroll_changed(self) -> None:
        """Restart debounce timer on scroll."""
        self._render_timer.start()

    def _on_render_timer(self) -> None:
        """Inform scene which pages are visible for rendering."""
        try:
            vp_rect = self.mapToScene(
                self.viewport().rect()).boundingRect()
            scene = self.scene()
            if scene and hasattr(scene, 'update_visible_pages'):
                scene.update_visible_pages(vp_rect)
        except RuntimeError:
            pass
