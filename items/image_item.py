"""Image item — QGraphicsItem for image annotations."""

from __future__ import annotations

import base64
import io

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPainterPath, QPen, QColor, QPixmap, QImage,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QStyleOptionGraphicsItem, QWidget,
    QGraphicsSceneHoverEvent, QGraphicsSceneMouseEvent,
)

from items.handle_item import HandlePosition


class ImageItem(QGraphicsItem):
    """An image annotation item.

    Uses local coordinates: setPos(topLeft), _rect = QRectF(0, 0, w, h).
    Handle children provide resize, move, and rotate functionality.
    Image data is stored as raw bytes for serialization.
    """

    MIN_SIZE: float = 16.0
    HIT_PADDING: float = 4.0
    HANDLE_POSITIONS: list[HandlePosition] = list(HandlePosition)

    def __init__(
        self,
        pixmap: QPixmap,
        rect: QRectF,
        page_index: int = -1,
        image_bytes: bytes | None = None,
        image_format: str = "PNG",
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap = pixmap
        self._rect: QRectF = QRectF(0, 0, rect.width(), rect.height())
        self._page_index: int = page_index
        self._is_selected: bool = False
        self._is_selected_custom: bool = False
        self._cached_br: QRectF | None = None

        # Store raw image bytes for serialization
        if image_bytes is not None:
            self._image_bytes: bytes = image_bytes
            self._image_format: str = image_format
        else:
            # Encode from pixmap
            self._image_format = "PNG"
            self._image_bytes = self._pixmap_to_bytes(pixmap, self._image_format)

        self.setPos(rect.topLeft())

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(2)

        # --- Handles (created as children) ---
        from items.image_handles import (
            ImageResizeHandle, ImageMoveHandle,
            ImageRotateHandle, ImageOptionsHandle,
        )

        self._handles: dict[HandlePosition, ImageResizeHandle] = {}
        for pos in HandlePosition:
            handle = ImageResizeHandle(pos, parent=self)
            self._handles[pos] = handle

        self._move_handle = ImageMoveHandle(parent=self)
        self._rotate_handle = ImageRotateHandle(parent=self)
        self._options_handle = ImageOptionsHandle(parent=self)

        self._update_handle_positions()
        self._set_handles_visible(False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pixmap_to_bytes(pixmap: QPixmap, fmt: str = "PNG") -> bytes:
        """Convert a QPixmap to raw bytes."""
        from PySide6.QtCore import QByteArray, QBuffer, QIODevice
        qba = QByteArray()
        qbuf = QBuffer(qba)
        qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.toImage().save(qbuf, fmt)
        qbuf.close()
        return bytes(qba.data())

    @staticmethod
    def from_image_file(file_path: str, pos: QPointF, page_index: int) -> ImageItem:
        """Create an ImageItem from an image file path."""
        with open(file_path, "rb") as f:
            image_bytes = f.read()

        # Determine format from extension
        ext = file_path.rsplit(".", 1)[-1].upper() if "." in file_path else "PNG"
        fmt_map = {"JPG": "JPEG", "JPEG": "JPEG", "PNG": "PNG", "WEBP": "WEBP"}
        image_format = fmt_map.get(ext, "PNG")

        pixmap = QPixmap()
        pixmap.loadFromData(image_bytes)
        if pixmap.isNull():
            raise ValueError(f"Could not load image: {file_path}")

        rect = QRectF(pos.x(), pos.y(), pixmap.width(), pixmap.height())
        return ImageItem(
            pixmap=pixmap,
            rect=rect,
            page_index=page_index,
            image_bytes=image_bytes,
            image_format=image_format,
        )

    @staticmethod
    def from_qimage(image: QImage, pos: QPointF, page_index: int) -> ImageItem:
        """Create an ImageItem from a QImage (e.g. from clipboard)."""
        pixmap = QPixmap.fromImage(image)
        if pixmap.isNull():
            raise ValueError("Could not convert QImage to QPixmap")

        rect = QRectF(pos.x(), pos.y(), pixmap.width(), pixmap.height())
        return ImageItem(
            pixmap=pixmap,
            rect=rect,
            page_index=page_index,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def page_index(self) -> int:
        return self._page_index

    def set_selected(self, selected: bool) -> None:
        self.prepareGeometryChange()
        self._is_selected = selected
        self._cached_br = None
        self.update()

    def set_selected_custom(self, selected: bool) -> None:
        """Show/hide handles + selection frame (called by scene)."""
        self.prepareGeometryChange()
        self._is_selected = selected
        self._is_selected_custom = selected
        self._cached_br = None
        self._set_handles_visible(selected)
        if selected:
            self._update_handle_positions()
        self.update()

    # ------------------------------------------------------------------
    # Rect accessors (scene coordinates)
    # ------------------------------------------------------------------

    def get_rect(self) -> QRectF:
        """Return the image rect in scene coordinates (copy)."""
        return QRectF(
            self.pos().x(),
            self.pos().y(),
            self._rect.width(),
            self._rect.height(),
        )

    def set_rect(self, rect: QRectF) -> None:
        """Set the image rect from scene coordinates."""
        self.prepareGeometryChange()
        self.setPos(rect.topLeft())
        self._rect = QRectF(0, 0, rect.width(), rect.height())
        self._cached_br = None
        self._update_handle_positions()
        self.update()

    # ------------------------------------------------------------------
    # Handle management
    # ------------------------------------------------------------------

    def _update_handle_positions(self) -> None:
        r = self._rect
        pad = 3.0

        positions = {
            HandlePosition.TOP_LEFT: QPointF(r.left() - pad, r.top() - pad),
            HandlePosition.TOP_RIGHT: QPointF(r.right() + pad, r.top() - pad),
            HandlePosition.MID_LEFT: QPointF(r.left() - pad, r.center().y()),
            HandlePosition.MID_RIGHT: QPointF(r.right() + pad, r.center().y()),
            HandlePosition.BOT_LEFT: QPointF(r.left() - pad, r.bottom() + pad),
            HandlePosition.BOT_RIGHT: QPointF(r.right() + pad, r.bottom() + pad),
        }

        for pos, point in positions.items():
            if pos in self._handles:
                self._handles[pos].setPos(point)

        if hasattr(self, '_move_handle'):
            padded = self._rect.adjusted(-pad, -pad, pad, pad)
            self._move_handle.update_position(padded)
        if hasattr(self, '_rotate_handle'):
            padded = self._rect.adjusted(-pad, -pad, pad, pad)
            self._rotate_handle.update_position(padded)
        if hasattr(self, '_options_handle') and self._options_handle.isVisible():
            padded = self._rect.adjusted(-pad, -pad, pad, pad)
            self._options_handle.update_position(padded)

    def _set_handles_visible(self, visible: bool) -> None:
        for handle in self._handles.values():
            handle.setVisible(visible)
        if hasattr(self, '_move_handle'):
            self._move_handle.setVisible(visible)
        if hasattr(self, '_rotate_handle'):
            self._rotate_handle.setVisible(visible)
        if hasattr(self, '_options_handle') and not visible:
            self._options_handle.hide()

    # ------------------------------------------------------------------
    # Resize via handles
    # ------------------------------------------------------------------

    def apply_handle_drag(
        self,
        handle_pos: HandlePosition,
        start_rect: QRectF,
        delta: QPointF,
        start_line_dir: int = 0,
    ) -> None:
        """Apply a handle drag to resize/reposition the image."""
        self.prepareGeometryChange()
        self._cached_br = None
        new_rect = QRectF(start_rect)

        from PySide6.QtGui import QGuiApplication
        shift = bool(QGuiApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)

        match handle_pos:
            case HandlePosition.TOP_LEFT:
                new_rect.setTopLeft(start_rect.topLeft() + delta)
            case HandlePosition.TOP_RIGHT:
                new_rect.setTopRight(start_rect.topRight() + delta)
            case HandlePosition.MID_LEFT:
                new_rect.setLeft(start_rect.left() + delta.x())
            case HandlePosition.MID_RIGHT:
                new_rect.setRight(start_rect.right() + delta.x())
            case HandlePosition.BOT_LEFT:
                new_rect.setBottomLeft(start_rect.bottomLeft() + delta)
            case HandlePosition.BOT_RIGHT:
                new_rect.setBottomRight(start_rect.bottomRight() + delta)

        if shift and handle_pos in (HandlePosition.TOP_LEFT, HandlePosition.TOP_RIGHT, HandlePosition.BOT_LEFT, HandlePosition.BOT_RIGHT):
            orig_w = max(self.MIN_SIZE, start_rect.width())
            orig_h = max(self.MIN_SIZE, start_rect.height())
            aspect = orig_w / orig_h
            w = new_rect.width()
            h = new_rect.height()
            
            if w < self.MIN_SIZE: w = self.MIN_SIZE
            if h < self.MIN_SIZE: h = self.MIN_SIZE
            
            if abs(w - orig_w) > abs(h - orig_h):
                h = w / aspect
            else:
                w = h * aspect
                
            if handle_pos == HandlePosition.TOP_LEFT:
                new_rect.setTopLeft(QPointF(start_rect.right() - w, start_rect.bottom() - h))
            elif handle_pos == HandlePosition.TOP_RIGHT:
                new_rect.setTopRight(QPointF(start_rect.left() + w, start_rect.bottom() - h))
            elif handle_pos == HandlePosition.BOT_LEFT:
                new_rect.setBottomLeft(QPointF(start_rect.right() - w, start_rect.top() + h))
            elif handle_pos == HandlePosition.BOT_RIGHT:
                new_rect.setBottomRight(QPointF(start_rect.left() + w, start_rect.top() + h))

        new_rect = new_rect.normalized()
        if new_rect.width() < self.MIN_SIZE:
            new_rect.setWidth(self.MIN_SIZE)
        if new_rect.height() < self.MIN_SIZE:
            new_rect.setHeight(self.MIN_SIZE)

        self.set_rect(new_rect)

    # ------------------------------------------------------------------
    # Options popup
    # ------------------------------------------------------------------

    def show_options_popup(self) -> None:
        """Toggle the inline options bar (Copy / Cut / Delete)."""
        if self._options_handle.isVisible():
            self._options_handle.hide()
        else:
            self._options_handle.update_position(self._rect)
            self._options_handle.show()

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        if self._cached_br is not None:
            return self._cached_br
        pad = self.HIT_PADDING
        if getattr(self, "_is_selected_custom", False):
            val = self._rect.adjusted(-pad - 50, -pad - 60, pad + 50, pad + 40)
        else:
            val = self._rect.adjusted(-pad, -pad, pad, pad)
        self._cached_br = val
        return val

    def shape(self) -> QPainterPath:
        """Precise hit-detection path — the image rectangle."""
        path = QPainterPath()
        path.addRect(self._rect)
        return path

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Draw the image scaled to the rect
        painter.drawPixmap(self._rect.toRect(), self._pixmap)

        # Selection frame (dashed blue border)
        hide_ui = getattr(self.scene(), "_is_rendering_thumbnail", False)
        if (self._is_selected or self._is_selected_custom) and not hide_ui:
            self._paint_selection(painter)

    def _paint_selection(self, painter: QPainter) -> None:
        """Blue dashed selection frame."""
        painter.save()
        pen = QPen(QColor("#3B7BF5"), 1.5, Qt.PenStyle.DashLine)
        pen.setDashPattern([6, 4])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setOpacity(1.0)
        pad = 3.0
        painter.drawRect(self._rect.adjusted(-pad, -pad, pad, pad))
        painter.restore()

    # ------------------------------------------------------------------
    # Hover / mouse
    # ------------------------------------------------------------------

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        from app.app_state import AppState
        if AppState().active_tool_name in {"selection", "hand"}:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        event.accept()

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self.setCursor(Qt.CursorShape.ArrowCursor)
        event.accept()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        from app.app_state import AppState

        # If selected, handle as move drag (for linear items analogy)
        if getattr(self, "_is_selected_custom", False):
            if event.button() == Qt.MouseButton.LeftButton:
                self._native_dragging = False
                self._click_scene_pos = event.scenePos()
                self._click_box_pos = QPointF(self.pos())
                event.accept()
                return

        if AppState().active_tool_name not in {"selection", "hand"}:
            event.ignore()
            return
        event.ignore()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if getattr(self, "_click_scene_pos", None) is not None:
            delta = event.scenePos() - self._click_scene_pos
            if not getattr(self, "_native_dragging", False):
                if abs(delta.x()) > 3.0 or abs(delta.y()) > 3.0:
                    self._native_dragging = True

            if self._native_dragging:
                self.setPos(self._click_box_pos + delta)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if getattr(self, "_click_scene_pos", None) is not None:
            if getattr(self, "_native_dragging", False):
                # Drag ended -> push undo command
                if self.pos() != self._click_box_pos:
                    from commands.move_image_command import MoveImageCommand
                    from core.undo_stack import get_stack
                    cmd = MoveImageCommand(
                        self, self._click_box_pos, self.pos(), self.scene(),
                    )
                    get_stack().push(cmd)
            else:
                pass

            self._native_dragging = False
            self._click_scene_pos = None
            self._click_box_pos = None
            event.accept()
            return

        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Bounding box resize support (for BoundingBoxHandleManager)
    # ------------------------------------------------------------------

    def apply_bounding_box_resize(self, new_br: QRectF) -> None:
        """Resize image to match new scene bounding box."""
        self.prepareGeometryChange()
        local_rect = self.mapFromScene(new_br).boundingRect()
        self._rect = local_rect
        self._cached_br = None
        self.update()

    def get_path_state(self) -> tuple:
        """Snapshot rect + position for undo."""
        return (QRectF(self._rect), QPointF(self.pos()))

    def set_path_state(self, path_or_rect, pos: QPointF) -> None:
        """Restore rect + position from undo snapshot."""
        self.prepareGeometryChange()
        self._rect = QRectF(path_or_rect)
        self.setPos(pos)
        self._cached_br = None
        self.update()

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        r = self._rect
        tp = self.transformOriginPoint()
        return {
            "type": "image",
            "version": 1,
            "rect": (self.pos().x(), self.pos().y(), r.width(), r.height()),
            "rotation": self.rotation(),
            "transform_origin": (tp.x(), tp.y()),
            "page_index": self._page_index,
            "pos": (self.pos().x(), self.pos().y()),
            "image_data": base64.b64encode(self._image_bytes).decode("ascii"),
            "image_format": self._image_format,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ImageItem:
        rx, ry, rw, rh = d["rect"]
        image_data = base64.b64decode(d["image_data"])
        image_format = d.get("image_format", "PNG")

        pixmap = QPixmap()
        pixmap.loadFromData(image_data)
        if pixmap.isNull():
            # Fallback: create a small red placeholder
            pixmap = QPixmap(int(rw) or 100, int(rh) or 100)
            pixmap.fill(QColor("#FF000044"))

        item = cls(
            pixmap=pixmap,
            rect=QRectF(rx, ry, rw, rh),
            page_index=d.get("page_index", -1),
            image_bytes=image_data,
            image_format=image_format,
        )
        item.setRotation(d.get("rotation", 0.0))
        if "transform_origin" in d:
            tx, ty = d["transform_origin"]
            item.setTransformOriginPoint(QPointF(tx, ty))
        return item
