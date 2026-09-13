"""Specialized child handles and vector cursor for SelectionBoxItem."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter,
    QPen,
    QColor,
    QBrush,
    QPainterPath,
    QPixmap,
    QPolygonF,
    QCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
)

from items.handle_item import ResizeHandleItem, HandlePosition
from items.rotate_handle_item import RotateHandleItem
from items.move_handle_item import MoveHandleItem
from items.options_handle_item import OptionsHandleItem

if TYPE_CHECKING:
    from items.selection_overlay_item import SelectionBoxItem

_ROTATION_CURSOR: QCursor | None = None

_RESIZE_BASE_ANGLES: dict[HandlePosition, float] = {
    HandlePosition.MID_LEFT: 0.0,
    HandlePosition.MID_RIGHT: 0.0,
    HandlePosition.TOP_CENTER: 90.0,
    HandlePosition.BOT_CENTER: 90.0,
    HandlePosition.TOP_LEFT: 45.0,
    HandlePosition.BOT_RIGHT: 45.0,
    HandlePosition.TOP_RIGHT: 135.0,
    HandlePosition.BOT_LEFT: 135.0,
}

_RESIZE_CURSOR_CACHE: dict[int, QCursor] = {}


def get_resize_cursor(angle: float) -> QCursor:
    """Return a crisp, high-DPI vector-drawn double-ended resize arrow cursor rotated by angle degrees."""
    quantized_angle = int(round(angle)) % 180
    cursor = _RESIZE_CURSOR_CACHE.get(quantized_angle)
    if cursor is not None:
        return cursor

    logical_size = 32
    app = QApplication.instance()
    screen = QApplication.primaryScreen() if app else None
    dpr = max(3.0, screen.devicePixelRatio() if screen else 3.0)
    pixel_size = int(logical_size * dpr)

    pixmap = QPixmap(pixel_size, pixel_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    p.translate(logical_size / 2.0, logical_size / 2.0)
    p.rotate(quantized_angle)

    L = 9.5
    head_len = 4.8
    head_w = 3.8
    stem_w = 1.1
    barbed = 0.6

    poly = QPolygonF([
        QPointF(L, 0),
        QPointF(L - head_len, head_w),
        QPointF(L - head_len + barbed, stem_w),
        QPointF(-L + head_len - barbed, stem_w),
        QPointF(-L + head_len, head_w),
        QPointF(-L, 0),
        QPointF(-L + head_len, -head_w),
        QPointF(-L + head_len - barbed, -stem_w),
        QPointF(L - head_len + barbed, -stem_w),
        QPointF(L - head_len, -head_w),
    ])

    outline_pen = QPen(
        QColor(0, 0, 0, 230),
        2.2,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    p.setPen(outline_pen)
    p.setBrush(QBrush(QColor(0, 0, 0, 230)))
    p.drawPolygon(poly)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(255, 255, 255, 255)))
    p.drawPolygon(poly)

    p.end()

    hotspot = int(logical_size / 2.0)
    cursor = QCursor(pixmap, hotspot, hotspot)
    _RESIZE_CURSOR_CACHE[quantized_angle] = cursor
    return cursor


def get_rotation_cursor() -> QCursor:
    """Return a crisp, high-DPI vector-drawn curved rotation arrow cursor with drop shadow."""
    global _ROTATION_CURSOR
    if _ROTATION_CURSOR is None:
        logical_size = 32
        dpr = 3.0
        pixel_size = int(logical_size * dpr)

        pixmap = QPixmap(pixel_size, pixel_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        pixmap.setDevicePixelRatio(dpr)

        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        cx, cy = logical_size / 2.0, logical_size / 2.0
        r = 7.5
        arc_rect = QRectF(cx - r, cy - r, r * 2, r * 2)

        # 1. Dark outline for contrast on both light and dark backgrounds
        shadow_pen = QPen(QColor(0, 0, 0, 240), 3.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(shadow_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        path1 = QPainterPath()
        path1.arcMoveTo(arc_rect, 25)
        path1.arcTo(arc_rect, 25, 130)
        p.drawPath(path1)

        path2 = QPainterPath()
        path2.arcMoveTo(arc_rect, 205)
        path2.arcTo(arc_rect, 205, 130)
        p.drawPath(path2)

        # Shadow arrowheads
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(0, 0, 0, 240)))
        arrow1_shadow = QPolygonF([
            QPointF(cx - r - 3.8, cy + 2.5),
            QPointF(cx - r + 3.8, cy + 2.5),
            QPointF(cx - r, cy - 3.8),
        ])
        arrow2_shadow = QPolygonF([
            QPointF(cx + r - 3.8, cy - 2.5),
            QPointF(cx + r + 3.8, cy - 2.5),
            QPointF(cx + r, cy + 3.8),
        ])
        p.drawPolygon(arrow1_shadow)
        p.drawPolygon(arrow2_shadow)

        # 2. Crisp White inner arrows
        white_pen = QPen(QColor("#ffffff"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(white_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path1)
        p.drawPath(path2)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#ffffff")))
        arrow1 = QPolygonF([
            QPointF(cx - r - 2.8, cy + 2.0),
            QPointF(cx - r + 2.8, cy + 2.0),
            QPointF(cx - r, cy - 3.0),
        ])
        arrow2 = QPolygonF([
            QPointF(cx + r - 2.8, cy - 2.0),
            QPointF(cx + r + 2.8, cy - 2.0),
            QPointF(cx + r, cy + 3.0),
        ])
        p.drawPolygon(arrow1)
        p.drawPolygon(arrow2)

        p.end()
        hotspot = int(logical_size / 2.0)
        _ROTATION_CURSOR = QCursor(pixmap, hotspot, hotspot)
    return _ROTATION_CURSOR


class SelectionResizeHandle(ResizeHandleItem):
    """Resize/Endpoint handle for SelectionBoxItem."""

    def __init__(self, position: HandlePosition, parent: QGraphicsItem) -> None:
        super().__init__(position, parent)
        self.update_cursor()

    def update_cursor(self) -> None:
        """Update the handle's cursor to match parent item's rotation in screen space."""
        if self._is_endpoint:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            return
        base_angle = _RESIZE_BASE_ANGLES.get(self._position, 0.0)
        rot = 0.0
        p = self.parentItem()
        while p is not None:
            rot += p.rotation()
            p = p.parentItem()
        total_angle = (base_angle + rot) % 180.0
        self.setCursor(get_resize_cursor(total_angle))

    def set_is_endpoint(self, is_endpoint: bool) -> None:
        super().set_is_endpoint(is_endpoint)
        self.update_cursor()

    def hoverEnterEvent(self, event) -> None:
        self.update_cursor()
        super().hoverEnterEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._dragging = True
        self._drag_start_pos = event.scenePos()
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        self._drag_start_rect = QRectF(overlay._bounding_rect)
        overlay._on_handle_press()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging or self._drag_start_pos is None or self._drag_start_rect is None:
            return
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        overlay._on_resize_handle_drag(
            self._position, self._drag_start_rect,
            self._drag_start_pos, event.scenePos(), shift,
        )
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.update()
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        overlay._on_handle_release("Skalieren")
        event.accept()


class SelectionRotateHandle(RotateHandleItem):
    """Rotate handle for SelectionBoxItem."""

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._dragging = True
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]

        center = overlay._bounding_rect.center()
        overlay._ensure_transform_origin_at_center()

        self._rotation_center = overlay.mapToScene(center)
        self._start_angle = self._angle_to(event.scenePos())
        self._last_angle = 0.0
        overlay._on_handle_press()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        delta_angle = self._angle_to(event.scenePos()) - self._start_angle
        raw_target_angle = overlay._drag_start_overlay_rotation + delta_angle

        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            target_angle = round(raw_target_angle / 45.0) * 45.0
            total_angle = target_angle - overlay._drag_start_overlay_rotation
        else:
            total_angle = delta_angle

        overlay._apply_rotation_from_start(total_angle)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.update()
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        overlay._on_handle_release("Rotieren")
        event.accept()


class SelectionMoveHandle(MoveHandleItem):
    """Move handle pill for SelectionBoxItem."""

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self._dragging = True
        self._drag_start_scene_pos = event.scenePos()
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        overlay._on_handle_press()
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging or self._drag_start_scene_pos is None:
            return
        delta = event.scenePos() - self._drag_start_scene_pos
        self._drag_start_scene_pos = event.scenePos()
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        overlay.apply_group_move(delta)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.update()
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        overlay._on_handle_release("Verschieben")
        event.accept()


class SelectionOptionsHandle(OptionsHandleItem):
    """Options handle bar for SelectionBoxItem."""

    def _execute_action(self, index: int) -> None:
        overlay: SelectionBoxItem = self.parentItem()  # type: ignore[assignment]
        if overlay is None:
            return
        if index == 0:
            overlay.copy_selected()
        elif index == 1:
            overlay.cut_selected()
        elif index == 2:
            overlay.delete_selected()
