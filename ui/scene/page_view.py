"""Graphics view for PDF pages – zoom, pan, and scroll-to-page."""

from PySide6.QtCore import (
    Qt,
    QTimer,
    Signal,
    QPointF,
)
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsView

from app.app_state import AppState
from core.tile_cache import MipLevel
from ui.scene.page_scene import PageScene
from ui.animations.kinetic import KineticScroller


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
    scroll_progress_changed = Signal(float)

    def __init__(self, scene: PageScene, parent: object = None) -> None:
        super().__init__(scene, parent)
        self._page_scene: PageScene = scene
        self._app_state: AppState = AppState()
        self._current_zoom: float = 1.0
        self._space_pressed: bool = False
        self._panning: bool = False
        self._pan_start_x: int = 0
        self._pan_start_y: int = 0
        self._kinetic_scroller = KineticScroller(self)

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
        self.setAcceptDrops(True)

        # Track scrolling to detect current visible page
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

        # Debounced render timer for virtual page rendering
        self._render_timer = QTimer()
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(30)
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
            self._update_mip_for_zoom()
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
        self._update_mip_for_zoom()

    def set_zoom(self, zoom: float) -> None:
        """Set the zoom to a specific level (no animation)."""
        zoom = max(self.ZOOM_MIN, min(self.ZOOM_MAX, zoom))
        self.resetTransform()
        self.scale(zoom, zoom)
        self._current_zoom = zoom
        self._app_state.zoom_factor = zoom
        self._update_mip_for_zoom()
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
            self._kinetic_scroller.on_mouse_press(event.x(), event.y())
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
            self._kinetic_scroller.on_mouse_move(event.x(), event.y())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: object) -> None:
        """Stop panning or forward to scene."""
        if self._panning:
            self._panning = False
            self._kinetic_scroller.on_mouse_release()
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
        """Detect which page is most visible after scrolling (binary search)."""
        try:
            viewport_rect = self.mapToScene(self.viewport().rect()).boundingRect()
            
            # Emit proportional scroll progress
            vbar = self.verticalScrollBar()
            if vbar.maximum() > 0:
                progress = vbar.value() / vbar.maximum()
                self.scroll_progress_changed.emit(progress)
                
        except RuntimeError:
            return
        viewport_center_y = viewport_rect.center().y()

        offsets = self._page_scene._page_y_offsets
        rects = self._page_scene._page_rects
        if not offsets:
            return

        # Binary search: find insertion point for viewport center
        import bisect
        idx = bisect.bisect_right(offsets, viewport_center_y)
        # idx is one past the last offset <= viewport_center_y
        # Check idx-1 and idx to find closest page center
        best_index = 0
        best_distance = float("inf")
        for candidate in (max(0, idx - 1), min(len(rects) - 1, idx)):
            if candidate < len(rects):
                page_center_y = rects[candidate].center().y()
                distance = abs(viewport_center_y - page_center_y)
                if distance < best_distance:
                    best_distance = distance
                    best_index = candidate

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
        """Start debounce timer on scroll if not already running."""
        if not self._render_timer.isActive():
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

    # ------------------------------------------------------------------
    # Mip level selection
    # ------------------------------------------------------------------

    def _update_mip_for_zoom(self) -> None:
        """Set the scene's current mip level based on the zoom factor."""
        if self._current_zoom < 0.6:
            mip = MipLevel.THUMB
        elif self._current_zoom < 1.2:
            mip = MipLevel.MEDIUM
        else:
            mip = MipLevel.FULL
        self._page_scene._current_mip = mip

    # ------------------------------------------------------------------
    # Drag & Drop for image files
    # ------------------------------------------------------------------

    _IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

    def dragEnterEvent(self, event) -> None:
        """Accept drag if it contains image files or image data."""
        mime = event.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    path = url.toLocalFile().lower()
                    if any(path.endswith(ext) for ext in self._IMAGE_EXTENSIONS):
                        event.acceptProposedAction()
                        return
        if mime.hasImage():
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        """Accept move during drag."""
        event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        """Handle image file drop — create ImageItem annotation."""
        import logging
        logger = logging.getLogger(__name__)

        mime = event.mimeData()
        drop_pos = self.mapToScene(event.position().toPoint())

        # Determine target page
        page_idx = self._page_scene.get_page_index_at(drop_pos)
        if page_idx < 0:
            # Drop outside any page — use current page
            page_idx = self._app_state.current_page
            page_rect = self._page_scene.get_page_rect(page_idx)
            if not page_rect.isEmpty():
                drop_pos = QPointF(page_rect.center().x(), page_rect.top() + 50)

        items_created = []

        if mime.hasUrls():
            for url in mime.urls():
                if not url.isLocalFile():
                    continue
                file_path = url.toLocalFile()
                if not any(file_path.lower().endswith(ext) for ext in self._IMAGE_EXTENSIONS):
                    continue
                try:
                    from items.image_item import ImageItem
                    item = ImageItem.from_image_file(file_path, drop_pos, page_idx)
                    # Scale down large images to fit page width
                    page_rect = self._page_scene.get_page_rect(page_idx)
                    if not page_rect.isEmpty() and item._rect.width() > page_rect.width() * 0.8:
                        scale = (page_rect.width() * 0.8) / item._rect.width()
                        new_w = item._rect.width() * scale
                        new_h = item._rect.height() * scale
                        from PySide6.QtCore import QRectF
                        item.set_rect(QRectF(drop_pos.x(), drop_pos.y(), new_w, new_h))
                    self._page_scene.addItem(item)
                    self._page_scene.add_item_to_registry(item)
                    items_created.append(item)
                    # Offset next image slightly
                    drop_pos = QPointF(drop_pos.x() + 20, drop_pos.y() + 20)
                except Exception as e:
                    logger.warning("Image drop failed: %s", e)

        elif mime.hasImage():
            try:
                from items.image_item import ImageItem
                from PySide6.QtGui import QImage
                image = QImage(mime.imageData())
                if not image.isNull():
                    item = ImageItem.from_qimage(image, drop_pos, page_idx)
                    # Scale down large images
                    page_rect = self._page_scene.get_page_rect(page_idx)
                    if not page_rect.isEmpty() and item._rect.width() > page_rect.width() * 0.8:
                        scale = (page_rect.width() * 0.8) / item._rect.width()
                        new_w = item._rect.width() * scale
                        new_h = item._rect.height() * scale
                        from PySide6.QtCore import QRectF
                        item.set_rect(QRectF(drop_pos.x(), drop_pos.y(), new_w, new_h))
                    self._page_scene.addItem(item)
                    self._page_scene.add_item_to_registry(item)
                    items_created.append(item)
            except Exception as e:
                logger.warning("Image clipboard drop failed: %s", e)

        if items_created:
            # Push undo command
            from commands.paste_items_command import PasteItemsCommand
            from core import undo_stack
            cmd = PasteItemsCommand(items_created, self._page_scene)
            undo_stack.push(cmd)

            # Select dropped items
            self._page_scene.set_selection(items_created)

            # Auto-switch to hand tool
            self._page_scene.tool_switch_requested.emit("hand")

            event.acceptProposedAction()
        else:
            event.ignore()
