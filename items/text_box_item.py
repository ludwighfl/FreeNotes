"""TextBox item – inline-editable text annotation with resize handles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF, QSizeF, QTimer, Signal
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QStyleOptionGraphicsItem,
    QWidget,
)

from app.app_state import AppState
from core.tool_style import ToolStyle
from core import undo_stack
from items.handle_item import ResizeHandleItem, HandlePosition
from items.text_box_input import TextBoxInputMixin
from items.text_box_formatting import TextBoxFormattingMixin
from items.text_box_pseudo_lists import TextBoxPseudoListMixin
from items.interactive_item import IRectResizable

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class TextBoxItem(TextBoxInputMixin, TextBoxFormattingMixin, TextBoxPseudoListMixin, QGraphicsObject, IRectResizable):
    """An inline-editable text annotation rendered via QTextDocument.

    Uses local coordinates: setPos(topLeft), _rect = QRectF(0, 0, w, h).
    8 HandleItem children provide resize functionality.
    ZValue = 15 (above strokes, below eraser cursor).

    Functionality is split across mixins:
        TextBoxInputMixin      – keyboard and mouse event handling
        TextBoxFormattingMixin – character and block formatting
    """

    MIN_WIDTH: float = 60.0
    MIN_HEIGHT: float = 24.0
    DEFAULT_WIDTH: float = 200.0
    PADDING: float = 8.0
    HANDLE_POSITIONS: list[HandlePosition] = list(HandlePosition)

    # Tools that are allowed to interact with TextBoxItems
    INTERACTIVE_TOOLS: frozenset[str] = frozenset({"text"})

    # Signal emitted when cursor position or format changes (QGraphicsObject supports signals)
    cursor_moved = Signal()
    editing_started = Signal()

    def __init__(
        self,
        rect: QRectF,
        style: ToolStyle,
        page_index: int = -1,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._style: ToolStyle = style.copy()
        self._page_index: int = page_index
        self._is_editing: bool = False
        self._is_selected_custom: bool = False

        # --- QTextDocument ---
        self._document = QTextDocument()
        font = QFont(style.font_family, max(style.font_size, 1))
        font.setBold(style.bold)
        font.setItalic(style.italic)
        font.setUnderline(style.underline)
        font.setStrikeOut(style.strikethrough)
        self._document.setDefaultFont(font)

        # --- QTextCursor ---
        self._cursor = QTextCursor(self._document)
        from PySide6.QtGui import QTextBlockFormat
        block_fmt = QTextBlockFormat()
        block_fmt.setAlignment(style.alignment)
        self._cursor.mergeBlockFormat(block_fmt)

        # --- Local rect + auto-size ---
        width = max(rect.width(), self.DEFAULT_WIDTH) if rect.width() > 0 else self.DEFAULT_WIDTH

        if rect.height() <= 0.0:
            # Height unknown — compute from font metrics (single line)
            fm = QFontMetricsF(self._document.defaultFont())
            min_height = fm.height() + self.PADDING * 2
        else:
            min_height = rect.height()

        self._rect: QRectF = QRectF(0, 0, width, min_height)
        self._min_size: QSizeF = QSizeF(width, min_height)
        self.setPos(rect.topLeft())

        self._document.setTextWidth(self._rect.width() - self.PADDING * 2)

        # --- Cursor blink ---
        self._blink_timer = QTimer()
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._toggle_cursor_blink)
        self._cursor_visible: bool = True

        # --- Mouse selection ---
        self._is_mouse_selecting: bool = False
        self._click_count: int = 0
        self._click_timer = QTimer()
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(300)
        self._click_timer.timeout.connect(self._reset_click_count)

        # --- Checkpoint-based undo ---
        self._undo_snapshot: str = self._document.toHtml()
        self._undo_pending: bool = False
        
        # --- List immutability check ---
        self.cursor_moved.connect(self._enforce_list_immutability)

        # --- Flags ---
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setZValue(6)
        self.setAcceptHoverEvents(True)

        # Handles are managed centrally by SelectionBoxItem

    # ==================================================================
    # QGraphicsItem interface
    # ==================================================================

    def boundingRect(self) -> QRectF:
        if getattr(self, "_is_selected_custom", False) or getattr(self, "_is_editing", False):
            return self._rect.adjusted(-50, -60, 50, 40)
        return self._rect.adjusted(-2, -2, 2, 2)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self._rect)
        return path

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Live selection preview: render text with blue tint overlay
        hide_ui = getattr(self.scene(), "_is_rendering_thumbnail", False)

        # Border painting managed centrally by SelectionBoxItem
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Text rendering
        painter.save()

        scene = self.scene()
        if scene and hasattr(scene, "get_page_rect") and self._page_index >= 0:
            page_rect = scene.get_page_rect(self._page_index)
            if page_rect.isValid() and not page_rect.isEmpty():
                p_path = QPainterPath()
                p_path.addRect(page_rect)
                painter.setClipPath(self.mapFromScene(p_path), Qt.ClipOperation.IntersectClip)

        painter.translate(self._rect.topLeft() + QPointF(self.PADDING, self.PADDING))
        text_clip = QRectF(
            0,
            0,
            self._rect.width() - self.PADDING * 2,
            self._rect.height() - self.PADDING * 2,
        )
        painter.setClipRect(text_clip, Qt.ClipOperation.IntersectClip)

        ctx = QAbstractTextDocumentLayout.PaintContext()
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Text, self._style.color)
        ctx.palette = palette

        # Cursor only when editing
        if self._is_editing and self._cursor_visible and not hide_ui:
            ctx.cursorPosition = self._cursor.position()
        else:
            ctx.cursorPosition = -1

        # Selection only when editing
        if self._is_editing and self._cursor.hasSelection() and not hide_ui:
            sel = QAbstractTextDocumentLayout.Selection()
            sel.cursor = self._cursor
            sel_fmt = QTextCharFormat()
            sel_fmt.setBackground(QColor("#3B7BF5"))
            sel_fmt.setForeground(QColor("#ffffff"))
            sel.format = sel_fmt
            ctx.selections = [sel]
        else:
            ctx.selections = []

        self._document.documentLayout().draw(painter, ctx)

        # Live selection preview: re-draw all text glyphs in blue
        if getattr(self, "_is_preview_highlight", False):
            ctx2 = QAbstractTextDocumentLayout.PaintContext()
            ctx2.palette = ctx.palette
            ctx2.cursorPosition = -1
            # Force blue foreground on ALL text via a full-document selection
            sel_all = QAbstractTextDocumentLayout.Selection()
            cur = QTextCursor(self._document)
            cur.movePosition(QTextCursor.MoveOperation.Start)
            cur.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
            sel_all.cursor = cur
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(59, 123, 245))
            sel_all.format = fmt
            ctx2.selections = [sel_all]
            self._document.documentLayout().draw(painter, ctx2)

        painter.restore()

    # ==================================================================
    # Handle management
    # ==================================================================

    def _update_handle_positions(self) -> None:
        r = self._rect
        positions = {
            HandlePosition.TOP_LEFT: QPointF(r.left(), r.top()),
            HandlePosition.TOP_RIGHT: QPointF(r.right(), r.top()),
            HandlePosition.MID_LEFT: QPointF(r.left(), r.center().y()),
            HandlePosition.MID_RIGHT: QPointF(r.right(), r.center().y()),
            HandlePosition.BOT_LEFT: QPointF(r.left(), r.bottom()),
            HandlePosition.BOT_RIGHT: QPointF(r.right(), r.bottom()),
        }
        for pos, point in positions.items():
            if pos in self._handles:
                self._handles[pos].setPos(point)
        if hasattr(self, '_move_handle'):
            self._move_handle.update_position(self._rect)
        if hasattr(self, '_rotate_handle'):
            self._rotate_handle.update_position(self._rect)
    def _update_handle_positions(self) -> None:
        pass

    def _set_handles_visible(self, visible: bool) -> None:
        pass

    # ==================================================================
    # Resize via handles
    # ==================================================================

    def apply_handle_drag(
        self,
        handle_pos: HandlePosition,
        start_rect: QRectF,
        delta: QPointF,
    ) -> None:
        """Apply a handle drag to resize/reposition the box.

        start_rect is in scene coordinates (from get_rect()).
        """
        new_rect = QRectF(start_rect)

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

        new_rect = new_rect.normalized()

        # Enforce minimum size
        if new_rect.width() < self.MIN_WIDTH:
            new_rect.setWidth(self.MIN_WIDTH)
        if new_rect.height() < self.MIN_HEIGHT:
            new_rect.setHeight(self.MIN_HEIGHT)

        self.set_rect(new_rect)

        # After manual resize: lock new minimum
        self._min_size = QSizeF(
            max(self._rect.width(), self.MIN_WIDTH),
            max(self._rect.height(), self.MIN_HEIGHT),
        )

    # ==================================================================
    # Rect accessors (scene coordinates)
    # ==================================================================

    def get_rect(self) -> QRectF:
        """Return the box rect in scene coordinates (copy)."""
        return QRectF(
            self.pos().x(),
            self.pos().y(),
            self._rect.width(),
            self._rect.height(),
        )

    def set_rect(self, rect: QRectF) -> None:
        """Set the box rect from scene coordinates, expanding height if needed to prevent clipping."""
        self.prepareGeometryChange()
        w, h = rect.width(), rect.height()
        self.setPos(rect.topLeft())
        self._document.setTextWidth(max(1.0, w - self.PADDING * 2))

        # Guarantee height is at least large enough to fit document content with padding
        min_doc_h = self._document.size().height() + self.PADDING * 2
        h = max(h, min_doc_h, self.MIN_HEIGHT)

        self._rect = QRectF(0, 0, w, h)
        self.setTransformOriginPoint(QPointF(w / 2.0, h / 2.0))
        self._update_handle_positions()
        self.update()

    def capture_state(self) -> dict:
        """Snapshot state for undo/redo."""
        return {
            "pos": QPointF(self.pos()),
            "rect": self.get_rect(),
            "rotation": self.rotation(),
            "transform_origin": QPointF(self.transformOriginPoint()),
            "html": self._document.toHtml(),
            "font_size": self._style.font_size,
        }

    def restore_state(self, state: dict) -> None:
        """Restore state from snapshot."""
        self.prepareGeometryChange()
        if "rotation" in state:
            self.setRotation(state["rotation"])
        if "transform_origin" in state:
            self.setTransformOriginPoint(state["transform_origin"])
        if "html" in state:
            self._document.setHtml(state["html"])
        if "font_size" in state:
            self._style.font_size = state["font_size"]
        if "rect" in state:
            self.set_rect(state["rect"])
        self.update()

    def apply_font_scale(self, scale_factor: float) -> None:
        """Scale all font sizes across the document proportionally with fine float precision."""
        if scale_factor <= 0.0 or abs(scale_factor - 1.0) < 0.0001:
            return

        default_font = self._document.defaultFont()
        old_pt = default_font.pointSizeF()
        if old_pt <= 0:
            old_pt = float(default_font.pointSize())
        new_default_pt = max(1.0, round(old_pt * scale_factor, 2))
        default_font.setPointSizeF(new_default_pt)
        default_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        default_font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        self._document.setDefaultFont(default_font)
        self._style.font_size = new_default_pt

        cursor = QTextCursor(self._document)
        cursor.beginEditBlock()

        block = self._document.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    fmt = fragment.charFormat()
                    current_pt = fmt.fontPointSize()
                    if current_pt > 0:
                        fmt.setFontPointSize(max(1.0, round(current_pt * scale_factor, 2)))
                    else:
                        fmt.setFontPointSize(new_default_pt)

                    pos = fragment.position()
                    length = fragment.length()
                    cursor.setPosition(pos)
                    cursor.setPosition(pos + length, QTextCursor.MoveMode.KeepAnchor)
                    cursor.setCharFormat(fmt)
                it += 1
            block = block.next()

        cursor.endEditBlock()

        # Re-verify text box height fits scaled document layout
        self._document.setTextWidth(max(1.0, self._rect.width() - self.PADDING * 2))
        min_doc_h = self._document.size().height() + self.PADDING * 2
        if self._rect.height() < min_doc_h:
            self.prepareGeometryChange()
            self._rect.setHeight(min_doc_h)
            self.setTransformOriginPoint(QPointF(self._rect.width() / 2.0, min_doc_h / 2.0))

        self.update()

    def get_geometry_rect(self) -> QRectF:
        return self.get_rect()

    def set_geometry_rect(self, rect: QRectF) -> None:
        self.set_rect(rect)

    def get_rotation_angle(self) -> float:
        return self.rotation()

    def set_rotation_angle(self, angle: float) -> None:
        self.setRotation(angle)

    def get_transform_origin(self) -> QPointF:
        return self.transformOriginPoint()

    def set_transform_origin(self, origin: QPointF) -> None:
        self.setTransformOriginPoint(origin)

    def apply_scale(self, sx: float, sy: float, pivot: QPointF) -> None:
        """Scale text box geometry rect and font size around a pivot point in scene space."""
        old_w = self._rect.width()
        old_h = self._rect.height()

        scale_factor = sy if sy > 0 else sx
        self.apply_font_scale(scale_factor)

        # Usable text wrapping width scales 1:1 with font size (sx) + 3.0px safety buffer against subpixel glyph rounding
        old_text_w = max(1.0, old_w - self.PADDING * 2)
        new_text_w = max(1.0, old_text_w * sx + 3.0)
        new_w = max(self.MIN_WIDTH, new_text_w + self.PADDING * 2)

        self._document.setTextWidth(new_text_w)
        min_doc_h = self._document.size().height() + self.PADDING * 2
        new_h = max(old_h * sy, min_doc_h, self.MIN_HEIGHT)

        origin_scene = self.mapToScene(self.transformOriginPoint())
        new_origin_scene = QPointF(
            pivot.x() + (origin_scene.x() - pivot.x()) * sx,
            pivot.y() + (origin_scene.y() - pivot.y()) * sy,
        )

        self.prepareGeometryChange()
        self._rect = QRectF(0, 0, new_w, new_h)
        new_origin = QPointF(new_w / 2.0, new_h / 2.0)
        self.setTransformOriginPoint(new_origin)
        self.setPos(new_origin_scene - new_origin)
        self.update()


    # ==================================================================
    # Hover cursors
    # ==================================================================

    def _is_text_tool_active(self) -> bool:
        """Check whether the currently active tool is the TextTool."""
        from tools.text_tool import TextTool
        scene = self.scene()
        if scene is not None and hasattr(scene, 'active_tool'):
            return isinstance(scene.active_tool, TextTool)
        return False

    def hoverEnterEvent(self, event) -> None:
        if self._is_text_tool_active():
            if self._is_editing:
                self.setCursor(Qt.CursorShape.IBeamCursor)
            else:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.unsetCursor()
        event.accept()

    def hoverMoveEvent(self, event) -> None:
        if self._is_text_tool_active():
            if self._is_editing:
                self.setCursor(Qt.CursorShape.IBeamCursor)
            else:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.unsetCursor()
        event.accept()

    def hoverLeaveEvent(self, event) -> None:
        self.unsetCursor()
        event.accept()

    # ==================================================================
    # Selection & editing
    # ==================================================================

    def start_editing(self) -> None:
        self.prepareGeometryChange()
        self._is_editing = True
        self._is_selected_custom = True
        self._blink_timer.start()
        self._cursor_visible = True
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if self.scene() is not None and hasattr(self.scene(), "_update_selection_overlay"):
            self.scene()._update_selection_overlay()
        self.update()
        self.editing_started.emit()

    def stop_editing(self) -> None:
        if not self._is_editing:
            return  # idempotent
        self.prepareGeometryChange()
        # Commit any pending undo checkpoint
        self._commit_undo_checkpoint()
        self._is_editing = False
        self._is_mouse_selecting = False
        self._blink_timer.stop()
        self._cursor_visible = False
        # Clear item-level cursor
        self.unsetCursor()
        # Clear selection to prevent ghost highlights
        pos = self._cursor.position()
        self._cursor.clearSelection()
        self._cursor.setPosition(pos, QTextCursor.MoveMode.MoveAnchor)
        if self.scene() is not None and hasattr(self.scene(), "_update_selection_overlay"):
            self.scene()._update_selection_overlay()
        self.update()
        self.cursor_moved.emit()

    def show_options_popup(self) -> None:
        """Toggle the options handle (Copy, Cut, Delete) for this box."""
        if self._options_handle.isVisible():
            self._options_handle.hide()
        else:
            self._options_handle.update_position(self._rect)
            self._options_handle.show()

    def clone(self) -> TextBoxItem:
        """Create an identical copy of this TextBox (slightly offset)."""
        new_box = TextBoxItem(
            rect=QRectF(self._rect),
            style=self._style,
            page_index=self._page_index,
        )
        new_box._document.setHtml(self._document.toHtml())
        new_box.setPos(self.pos() + QPointF(12, 12))
        new_box.setRotation(self.rotation())
        new_box.setTransformOriginPoint(self.transformOriginPoint())
        return new_box

    def set_selected_custom(self, selected: bool) -> None:
        self.prepareGeometryChange()
        self._is_selected_custom = selected
        self._set_handles_visible(False)
        self.setZValue(6)
        if not selected:
            self.stop_editing()
            # Ensure cursor selection is cleared
            pos = self._cursor.position()
            self._cursor.setPosition(pos, QTextCursor.MoveMode.MoveAnchor)
            # Auto-delete empty box
            if self._document.toPlainText().strip() == "":
                scene = self.scene()
                if scene is not None:
                    scene.removeItem(self)
                    from ui.scene.page_scene import PageScene

                    if isinstance(scene, PageScene):
                        scene.remove_item_from_registry(self)
        self.update()

    def _toggle_cursor_blink(self) -> None:
        self._cursor_visible = not self._cursor_visible
        self.update()

    # ==================================================================
    # Auto-resize
    # ==================================================================

    def _auto_resize(self) -> None:
        """Recalculate height after text modification while respecting current width."""
        # Force text to wrap at current visual width
        current_width = self._rect.width()
        new_text_width = current_width - self.PADDING * 2
        if abs(self._document.textWidth() - new_text_width) > 0.5:
            self._document.setTextWidth(new_text_width)

        # Height at this width
        natural_height = self._document.size().height() + self.PADDING * 2
        natural_height = max(natural_height, self._min_size.height())

        # Only update if actually changed (performance)
        height_changed = abs(natural_height - self._rect.height()) > 0.5

        if height_changed:
            self.prepareGeometryChange()

            self._rect.setHeight(natural_height)
            self._update_handle_positions()
            self.update()

    def _on_cursor_moved(self) -> None:
        """Update display and emit signal after cursor navigation."""
        self.update()
        self.cursor_moved.emit()

    def _on_text_modified(self) -> None:
        """Called after every text change (keyPress, paste, etc.)."""
        self._auto_resize()
        self.cursor_moved.emit()

    # ==================================================================
    # Checkpoint-based undo
    # ==================================================================

    def _mark_undo_pending(self) -> None:
        """Mark that there are unsaved changes; snapshot taken on first call."""
        if not self._undo_pending:
            self._undo_snapshot = self._document.toHtml()
            self._undo_pending = True

    def _commit_undo_checkpoint(self) -> None:
        """Save current state as an undo step if there are pending changes."""
        if not self._undo_pending:
            return
        current_html = self._document.toHtml()
        if current_html == self._undo_snapshot:
            self._undo_pending = False
            return
        from commands.edit_text_command import EditTextCommand
        scene = self.scene()
        if scene is None:
            return
        cmd = EditTextCommand(
            self,
            self._undo_snapshot,
            current_html,
            scene,
        )
        undo_stack.push(cmd)
        self._undo_snapshot = current_html
        self._undo_pending = False

    # ==================================================================
    # Properties
    # ==================================================================

    @property
    def page_index(self) -> int:
        return self._page_index

    @property
    def document(self) -> QTextDocument:
        return self._document

    @property
    def plain_text(self) -> str:
        return self._document.toPlainText()

    @plain_text.setter
    def plain_text(self, value: str) -> None:
        self._document.setPlainText(value)
        self._cursor = QTextCursor(self._document)
        self._auto_resize()
        self.update()

    @property
    def html_text(self) -> str:
        return self._document.toHtml()

    @html_text.setter
    def html_text(self, value: str) -> None:
        self._document.setHtml(value)
        self._cursor = QTextCursor(self._document)
        self._auto_resize()
        self.update()

    @property
    def style(self) -> ToolStyle:
        return self._style

    # ==================================================================
    # Serialization (for clone_page_annotations)
    # ==================================================================

    def to_dict(self) -> dict:
        r = self.get_rect()
        return {
            "type": "textbox",
            "html": self._document.toHtml(),
            "rect": (r.x(), r.y(), r.width(), r.height()),
            "rotation": self.rotation(),
            "page_index": self._page_index,
            "pos": (self.pos().x(), self.pos().y()),
            "style_color": self._style.color.name(),
            "font_family": self._style.font_family,
            "font_size": self._style.font_size,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TextBoxItem:
        rx, ry, rw, rh = d["rect"]
        style = ToolStyle(
            color=QColor(d.get("style_color", "#000000")),
            font_family=d.get("font_family", "Roboto"),
            font_size=d.get("font_size", 14),
        )
        item = cls(
            rect=QRectF(rx, ry, rw, rh),
            style=style,
            page_index=d.get("page_index", -1),
        )
        item._document.setHtml(d["html"])
        item.setRotation(d.get("rotation", 0.0))
        return item
