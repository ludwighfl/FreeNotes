"""TextBox list operations mixin – simulated lists via text replacement."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QTextBlockFormat,
    QTextCursor,
    QFontMetricsF,
)

if TYPE_CHECKING:
    from PySide6.QtGui import QTextDocument


class TextBoxPseudoListMixin:
    """Mixin providing text-based simulated list operations for TextBoxItem.

    Expects the host class to provide:
        _cursor: QTextCursor
        _document: QTextDocument
        _undo_snapshot: str
        _undo_pending: bool
        _commit_undo_checkpoint(): method
        _push_format_command(): method
        _auto_resize(): method
        update(): method
        cursor_moved: Signal
    """

    # Maps trigger strings to their standardized list prefix
    # Pattern: [Trigger regex, Replacement string]
    _LIST_TYPES = {
        "-": "\u2011\u00A0",
        "*": "•\u00A0",
    }

    # Regex patterns for matching existing active list markers at the start of a line
    _R_BULLET = re.compile(r"^[•\u2011-]\s")
    _R_DECIMAL = re.compile(r"^(\d+)\.\s")
    _R_ALPHA_LOWER = re.compile(r"^([a-z])\)\s")
    _R_ALPHA_UPPER = re.compile(r"^([A-Z])\)\s")

    def _get_marker_at_block_start(self, cursor: QTextCursor) -> str | None:
        """Return the list marker at the start of the block, or None if no list."""
        text = cursor.block().text()
        
        # Check bullets first (fastest)
        m = self._R_BULLET.match(text)
        if m: return m.group(0)
        
        m = self._R_DECIMAL.match(text)
        if m: return m.group(0)
        
        m = self._R_ALPHA_LOWER.match(text)
        if m: return m.group(0)
        
        m = self._R_ALPHA_UPPER.match(text)
        if m: return m.group(0)
        
        return None

    def _get_next_marker(self, current_marker: str) -> str:
        """Given a marker like '1. ' or 'a) ', return '2. ' or 'b) '."""
        # Decimal
        m = self._R_DECIMAL.match(current_marker)
        if m:
            num = int(m.group(1))
            return f"{num + 1}.\u00A0"
            
        # Lower alpha
        m = self._R_ALPHA_LOWER.match(current_marker)
        if m:
            char = m.group(1)
            next_char = 'a' if char == 'z' else chr(ord(char) + 1)
            return f"{next_char})\u00A0"
            
        # Upper alpha
        m = self._R_ALPHA_UPPER.match(current_marker)
        if m:
            char = m.group(1)
            next_char = 'A' if char == 'Z' else chr(ord(char) + 1)
            return f"{next_char})\u00A0"
            
        # Bullets return themselves
        return current_marker

    def _apply_hanging_indent(self, cursor: QTextCursor, marker: str) -> None:
        """Measure the marker width and apply a hanging indent to the block."""
        fm = QFontMetricsF(cursor.charFormat().font())
        width = fm.horizontalAdvance(marker)
        
        block_fmt = cursor.blockFormat()
        # Left margin pushes the whole block to the right
        block_fmt.setLeftMargin(width)
        # Negative text indent pulls the first line back to the left
        block_fmt.setTextIndent(-width)
        
        cursor.setBlockFormat(block_fmt)

    def _remove_hanging_indent(self, cursor: QTextCursor) -> None:
        """Clear any list-related indentation formats."""
        block_fmt = cursor.blockFormat()
        block_fmt.setLeftMargin(0)
        block_fmt.setTextIndent(0)
        cursor.setBlockFormat(block_fmt)

    def _try_auto_list(self) -> bool:
        """Check if current word before cursor is a list trigger (e.g. '-', '1.', 'a)')."""
        block_text = self._cursor.block().text()
        pos_in_block = self._cursor.positionInBlock()
        prefix = block_text[:pos_in_block].strip()

        replacement = None
        
        # 1. Exact matches (*, -)
        if prefix in self._LIST_TYPES:
            replacement = self._LIST_TYPES[prefix]
        # 2. Pattern matches (1., a), A))
        elif re.match(r"^\d+\.$", prefix):
            replacement = f"{prefix}\u00A0"
        elif re.match(r"^[a-z]\)$", prefix):
            replacement = f"{prefix}\u00A0"
        elif re.match(r"^[A-Z]\)$", prefix):
            replacement = f"{prefix}\u00A0"

        if replacement is None:
            return False

        # If already at the start of a list block, don't trigger (prevent recursive)
        if self._get_marker_at_block_start(self._cursor):
            return False

        # Trigger matched → delete trigger text and replace with marker
        old_html = self._document.toHtml()
        
        self._cursor.beginEditBlock()
        
        # Move cursor back to start of trigger, select, and replace
        # Note: we use prefix length to delete exactly what the user typed before the space
        self._cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(block_text[:pos_in_block]))
        self._cursor.insertText(replacement)
        
        # Apply the hanging indent logic
        self._apply_hanging_indent(self._cursor, replacement)
        
        self._cursor.endEditBlock()
        
        new_html = self._document.toHtml()
        self._push_format_command(old_html, new_html, "Liste gestartet")
        
        self._auto_resize()
        self.update()
        self.cursor_moved.emit()
        return True

    def _handle_list_enter(self, event) -> bool:
        """Handle Enter key when in a list block. Returns True if handled."""
        marker = self._get_marker_at_block_start(self._cursor)
        if not marker:
            return False
            
        # Is the cursor at the very end of the line?
        at_end = self._cursor.positionInBlock() == len(self._cursor.block().text())
        
        old_html = self._document.toHtml()
        self._cursor.beginEditBlock()
        
        if at_end:
            # Native list-like continuation
            next_marker = self._get_next_marker(marker)
            self._cursor.insertBlock()
            
            # The indent carries over by default in Qt, which is great, 
            # but the new marker might have a different width (e.g. 9. vs 10.) 
            # so we re-apply it based on the new marker text width.
            self._cursor.insertText(next_marker)
            self._apply_hanging_indent(self._cursor, next_marker)
        else:
            # Cursor explicitly placed in middle of line -> break list logic
            self._cursor.insertBlock()
            self._remove_hanging_indent(self._cursor)
            
        self._cursor.endEditBlock()
        
        new_html = self._document.toHtml()
        self._push_format_command(old_html, new_html, "Neue Zeile")
        
        self._auto_resize()
        self.update()
        self.cursor_moved.emit()
        event.accept()
        return True

    def _handle_list_backspace(self, event) -> bool:
        """Handle Backspace. Returns True if handled explicitly by list logic."""
        marker = self._get_marker_at_block_start(self._cursor)
        if not marker:
            return False
            
        pos = self._cursor.positionInBlock()
        marker_len = len(marker)
        
        # Backspace pressed directly after the list marker
        if pos == marker_len and not self._cursor.hasSelection():
            old_html = self._document.toHtml()
            self._cursor.beginEditBlock()
            
            # Remove the marker
            self._cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            self._cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, marker_len)
            self._cursor.removeSelectedText()
            
            # Remove indent
            self._remove_hanging_indent(self._cursor)
            
            self._cursor.endEditBlock()
            
            new_html = self._document.toHtml()
            self._push_format_command(old_html, new_html, "Liste entfernt")
            
            self._auto_resize()
            self.update()
            self.cursor_moved.emit()
            event.accept()
            return True
            
        return False

    def _enforce_list_immutability(self) -> None:
        """Push cursor right if it tries to enter the list marker."""
        marker = self._get_marker_at_block_start(self._cursor)
        if not marker:
            return
            
        marker_len = len(marker)
        pos = self._cursor.positionInBlock()
        
        if pos < marker_len:
            # Cursor is inside the marker!
            # Move it to the exact boundary of the marker.
            block_start = self._cursor.block().position()
            target_pos = block_start + marker_len
            
            # If there's an active selection, we must preserve the anchor correctly.
            mode = QTextCursor.MoveMode.KeepAnchor if self._cursor.hasSelection() else QTextCursor.MoveMode.MoveAnchor
            self._cursor.setPosition(target_pos, mode)
            self.update()
