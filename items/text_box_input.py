"""TextBox input mixin – keyboard and mouse event handling."""

from __future__ import annotations

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QFont,
    QKeyEvent,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
)

from app.app_state import AppState


class TextBoxInputMixin:
    """Mixin providing keyboard and mouse input handling for TextBoxItem.

    Expects the host class to provide:
        _is_editing: bool
        _cursor: QTextCursor
        _document: QTextDocument
        _undo_snapshot: str
        _undo_pending: bool
        _is_mouse_selecting: bool
        _click_count: int
        _click_timer: QTimer
        PADDING: float
        INTERACTIVE_TOOLS: frozenset[str]
        _mark_undo_pending(): method
        _commit_undo_checkpoint(): method
        _on_cursor_moved(): method
        _on_text_modified(): method
        _auto_resize(): method
        _handle_enter(): method  (from TextBoxListsMixin)
        _try_auto_list(): method (from TextBoxListsMixin)
        _push_format_command(): method (from TextBoxFormattingMixin)
        apply_bold(): method (from TextBoxFormattingMixin)
        apply_italic(): method (from TextBoxFormattingMixin)
        apply_underline(): method (from TextBoxFormattingMixin)
        apply_strikethrough(): method (from TextBoxFormattingMixin)
        start_editing(): method
        stop_editing(): method
        set_selected_custom(): method
        update(): method
        cursor_moved: Signal
        scene(): method
    """

    # ==================================================================
    # Key input
    # ==================================================================

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._is_editing:
            event.ignore()
            return

        key = event.key()
        modifiers = event.modifiers()
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        # ── Block 1: Ctrl-Shortcuts ────────────────────────────────
        if ctrl:
            if not shift:
                if key == Qt.Key.Key_B:
                    fmt = self._cursor.charFormat()
                    self.apply_bold(fmt.fontWeight() < QFont.Weight.Bold)
                    event.accept(); return
                elif key == Qt.Key.Key_I:
                    fmt = self._cursor.charFormat()
                    self.apply_italic(not fmt.fontItalic())
                    event.accept(); return
                elif key == Qt.Key.Key_U:
                    fmt = self._cursor.charFormat()
                    self.apply_underline(not fmt.fontUnderline())
                    event.accept(); return
                elif key == Qt.Key.Key_A:
                    self._cursor.select(QTextCursor.SelectionType.Document)
                    self._on_cursor_moved()
                    event.accept(); return
            if shift and key == Qt.Key.Key_S:
                fmt = self._cursor.charFormat()
                self.apply_strikethrough(not fmt.fontStrikeOut())
                event.accept(); return
            # Other Ctrl combos (e.g. Ctrl+Z) → pass to scene
            event.ignore(); return

        # ── Block 2: Navigation ────────────────────────────────────
        move_mode = (
            QTextCursor.MoveMode.KeepAnchor
            if shift
            else QTextCursor.MoveMode.MoveAnchor
        )
        nav_map = {
            Qt.Key.Key_Left: QTextCursor.MoveOperation.Left,
            Qt.Key.Key_Right: QTextCursor.MoveOperation.Right,
            Qt.Key.Key_Up: QTextCursor.MoveOperation.Up,
            Qt.Key.Key_Down: QTextCursor.MoveOperation.Down,
            Qt.Key.Key_Home: QTextCursor.MoveOperation.StartOfLine,
            Qt.Key.Key_End: QTextCursor.MoveOperation.EndOfLine,
        }
        if key in nav_map:
            self._cursor.movePosition(nav_map[key], move_mode)
            self._on_cursor_moved()
            event.accept(); return

        # ── Block 3: Delete ────────────────────────────────────────
        if key == Qt.Key.Key_Backspace:
            if self._handle_list_backspace(event):
                return

            self._mark_undo_pending()
            if self._cursor.hasSelection():
                self._cursor.removeSelectedText()
            else:
                self._cursor.deletePreviousChar()
            self._on_text_modified()
            self._on_cursor_moved()
            event.accept(); return

        if key == Qt.Key.Key_Delete:
            self._mark_undo_pending()
            if self._cursor.hasSelection():
                self._cursor.removeSelectedText()
            else:
                self._cursor.deleteChar()
            self._on_text_modified()
            self._on_cursor_moved()
            event.accept(); return

        # ── Block 4: Enter ─────────────────────────────────────────
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._handle_list_enter(event):
                return

            self._commit_undo_checkpoint()
            self._cursor.insertBlock()
            self._undo_snapshot = self._document.toHtml()
            self._undo_pending = False
            self._auto_resize()
            self.update()
            self._on_cursor_moved()
            event.accept(); return

        # ── Block 5: Space (explicit, before printable) ────────────
        if key == Qt.Key.Key_Space:
            block_text = self._cursor.block().text()
            pos_in_block = self._cursor.positionInBlock()
            prefix = block_text[:pos_in_block]

            self._mark_undo_pending()
            self._commit_undo_checkpoint()

            if self._try_auto_list():
                pass # List triggered and handled
            elif prefix.endswith("->"):
                old_html = self._document.toHtml()
                self._cursor.beginEditBlock()
                self._cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, 2)
                self._cursor.insertText("→ ")
                self._cursor.endEditBlock()
                new_html = self._document.toHtml()
                self._push_format_command(old_html, new_html, "Pfeil rechts")
            elif prefix.endswith("<-"):
                old_html = self._document.toHtml()
                self._cursor.beginEditBlock()
                self._cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, 2)
                self._cursor.insertText("← ")
                self._cursor.endEditBlock()
                new_html = self._document.toHtml()
                self._push_format_command(old_html, new_html, "Pfeil links")
            else:
                self._cursor.insertText(" ")

            self._undo_snapshot = self._document.toHtml()
            self._undo_pending = False
            self._on_text_modified()
            self._on_cursor_moved()
            event.accept(); return

        # ── Block 6: Escape ────────────────────────────────────────
        if key == Qt.Key.Key_Escape:
            self.stop_editing()
            self.set_selected_custom(False)
            event.accept(); return

        # ── Block 7: Printable characters ──────────────────────────
        text = event.text()
        if text:
            if text.isprintable():
                self._mark_undo_pending()
                self._cursor.insertText(text)
                self._on_text_modified()
                self._on_cursor_moved()
                event.accept(); return

        event.ignore()

    # ==================================================================
    # Mouse events
    # ==================================================================

    def _pos_to_char_index(self, item_pos: QPointF) -> int:
        """Convert item-local position to character index in document."""
        doc_pos = item_pos - QPointF(self.PADDING, self.PADDING)
        char_pos = self._document.documentLayout().hitTest(
            doc_pos, Qt.HitTestAccuracy.FuzzyHit
        )
        return max(0, char_pos)

    def _reset_click_count(self) -> None:
        self._click_count = 0

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        # Tool filter: only interactive tools may interact
        active_tool = AppState().active_tool_name
        if active_tool not in self.INTERACTIVE_TOOLS:
            event.ignore()
            return

        # Hand/selection tool: request tool switch, then continue to edit
        if active_tool in {"hand", "selection"}:
            scene = self.scene()
            if not self._is_editing and scene:
                scene.request_tool_switch("text")

        # Multi-click detection
        if self._click_timer.isActive():
            self._click_count += 1
        else:
            self._click_count = 1
        self._click_timer.start()

        char_idx = self._pos_to_char_index(event.pos())

        match self._click_count:
            case 1:
                # Single click: position cursor, clear selection
                self._cursor.setPosition(char_idx)
                self._is_mouse_selecting = True
            case 2:
                # Double click: select word
                self._cursor.setPosition(char_idx)
                self._cursor.select(QTextCursor.SelectionType.WordUnderCursor)
                self._is_mouse_selecting = False
            case 3:
                # Triple click: select paragraph
                self._cursor.setPosition(char_idx)
                self._cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                self._is_mouse_selecting = False
            case _:
                # 4+ clicks: select all
                self._cursor.select(QTextCursor.SelectionType.Document)
                self._is_mouse_selecting = False

        if not self._is_editing:
            self.start_editing()

        self.update()
        self.cursor_moved.emit()
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if not self._is_mouse_selecting:
            super().mouseMoveEvent(event)
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not self._is_editing:
            return

        char_idx = self._pos_to_char_index(event.pos())

        # Extend selection: keep anchor, move position
        anchor = self._cursor.anchor()
        self._cursor.setPosition(anchor)
        self._cursor.setPosition(char_idx, QTextCursor.MoveMode.KeepAnchor)

        self.update()
        self.cursor_moved.emit()
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self._is_mouse_selecting = False
        event.accept()

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        # Handled via click-count in mousePressEvent; forward there
        self.mousePressEvent(event)

    def focusOutEvent(self, event) -> None:
        # Don't stop editing on focus out to our own handles
        focus_item = self.scene().focusItem() if self.scene() else None
        if focus_item is not None and focus_item.parentItem() is self:
            return
        self.stop_editing()
        super().focusOutEvent(event)
