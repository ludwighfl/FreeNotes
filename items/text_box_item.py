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

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class TextBoxItem(TextBoxInputMixin, TextBoxFormattingMixin, TextBoxPseudoListMixin, QGraphicsObject):
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
    INTERACTIVE_TOOLS: frozenset[str] = frozenset({"text", "hand"})

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
        self.setZValue(15)
        self.setAcceptHoverEvents(True)

        # --- 6 Resize handles (corners + left/right edges) ---
        self._handles: dict[HandlePosition, ResizeHandleItem] = {}
        for pos in HandlePosition:
            handle = ResizeHandleItem(pos, parent=self)
            self._handles[pos] = handle

        # --- Move handle (top-center pill) ---
        from items.move_handle_item import MoveHandleItem
        self._move_handle = MoveHandleItem(parent=self)

        # --- Rotate handle (bottom-center circle) ---
        from items.rotate_handle_item import RotateHandleItem
        self._rotate_handle = RotateHandleItem(parent=self)

        # --- Options handle (Copy/Cut/Delete bar) ---
        from items.options_handle_item import OptionsHandleItem
        self._options_handle = OptionsHandleItem(parent=self)

        self._update_handle_positions()
        self._set_handles_visible(False)

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
        
        hide_ui = getattr(self.scene(), "_is_rendering_thumbnail", False)

        # Border – dashed blue when selected/editing
        if (self._is_selected_custom or self._is_editing) and not hide_ui:
            pen = QPen(QColor("#3B7BF5"), 1.5, Qt.PenStyle.DashLine)
            pen.setDashPattern([6, 4])
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._rect)

        # Text rendering
        painter.save()
        painter.translate(self._rect.topLeft() + QPointF(self.PADDING, self.PADDING))
        text_clip = QRectF(
            0,
            0,
            self._rect.width() - self.PADDING * 2,
            self._rect.height() - self.PADDING * 2,
        )
        painter.setClipRect(text_clip)

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
        if hasattr(self, '_options_handle') and self._options_handle.isVisible():
            self._options_handle.update_position(self._rect)

    def _set_handles_visible(self, visible: bool) -> None:
        from shiboken6 import isValid  # noqa: E402
        for handle in self._handles.values():
            if isValid(handle):
                handle.setVisible(visible)
        if hasattr(self, '_move_handle') and isValid(self._move_handle):
            self._move_handle.setVisible(visible)
        if hasattr(self, '_rotate_handle') and isValid(self._rotate_handle):
            self._rotate_handle.setVisible(visible)
        # Options handle is toggled separately via right-click; hide when handles hide
        if hasattr(self, '_options_handle') and not visible and isValid(self._options_handle):
            self._options_handle.hide()

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
        """Set the box rect from scene coordinates."""
        self.prepareGeometryChange()
        self.setPos(rect.topLeft())
        self._rect = QRectF(0, 0, rect.width(), rect.height())
        self._document.setTextWidth(self._rect.width() - self.PADDING * 2)
        self._update_handle_positions()
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
        self._set_handles_visible(True)
        self._blink_timer.start()
        self._cursor_visible = True
        self.setFocus(Qt.FocusReason.MouseFocusReason)
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
        self._set_handles_visible(selected)
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
            font_family=d.get("font_family", "Segoe UI"),
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
