"""Graphics view for PDF pages – zoom, pan, and scroll-to-page."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal, QPointF
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QGraphicsView

from app.app_state import AppState
from ui.scene.page_scene import PageScene
from ui.animations.kinetic import KineticScroller
from ui.animations.scroll import ScrollAnimation

from ui.scene.page_view_navigation_mixin import PageViewNavigationMixin
from ui.scene.page_view_gesture_mixin import PageViewGestureMixin


class PageView(PageViewNavigationMixin, PageViewGestureMixin, QGraphicsView):
    """QGraphicsView with zoom (Ctrl+Scroll), pan (Space+Drag / Middle-mouse),
    and smooth scroll-to-page support.

    Features are modularly split into mixins:
    - PageViewNavigationMixin: Handles zoom, scroll-to-page, and visible page detection.
    - PageViewGestureMixin: Handles touch, gestures, tablet, and panning events.
    """

    ZOOM_FACTOR: float = 1.15
    ZOOM_MIN: float = 0.1
    ZOOM_MAX: float = 5.0

    visible_page_changed = Signal(int)

    _IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

    def __init__(self, scene: PageScene, parent: object = None) -> None:
        super().__init__(scene, parent)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.grabGesture(Qt.GestureType.PinchGesture)
        self._touch_active: bool = False
        self._gesture_active: bool = False
        self._last_touch_distance: float = 0.0
        self._last_touch_center: QPointF = QPointF()
        self._page_scene: PageScene = scene
        self._app_state: AppState = AppState()
        self._current_zoom: float = 1.0
        self._space_pressed: bool = False
        self._panning: bool = False
        self._pan_start_x: int = 0
        self._pan_start_y: int = 0
        self._kinetic_scroller = KineticScroller(self)
        self._scroll_anim = ScrollAnimation(self)
        self._scroll_anim.finished.connect(self._on_scroll)
        self._scroll_anim.finished.connect(self._on_render_timer)
        self._target_zoom: float = 1.0

        # Smooth zoom animation
        from PySide6.QtCore import QVariantAnimation, QEasingCurve
        self._zoom_anim = QVariantAnimation(self)
        self._zoom_anim.setDuration(250)
        self._zoom_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._zoom_anim.valueChanged.connect(self._on_zoom_anim_value_changed)

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

        # Track scrolling to detect current visible page and direction
        self._last_scroll_y = 0
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

        # Debounced render timer for virtual page rendering
        self._render_timer = QTimer()
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(50)
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
        self._restore_tool_cursor()
        super().enterEvent(event)

    # ------------------------------------------------------------------
    # Drag & Drop for image files
    # ------------------------------------------------------------------

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

        page_idx = self._page_scene.get_page_index_at(drop_pos)
        if page_idx < 0:
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
            from commands.paste_items_command import PasteItemsCommand
            from core import undo_stack
            cmd = PasteItemsCommand(items_created, self._page_scene)
            undo_stack.push(cmd)

            self._page_scene.set_selection(items_created)
            self._page_scene.tool_switch_requested.emit("hand")
            event.acceptProposedAction()
        else:
            event.ignore()
