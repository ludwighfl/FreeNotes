"""TextBox formatting mixin – character and block formatting operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QTextBlockFormat,
    QTextCharFormat,
)

from core import undo_stack

if TYPE_CHECKING:
    from PySide6.QtGui import QTextCursor, QTextDocument


class TextBoxFormattingMixin:
    """Mixin providing character and block formatting methods for TextBoxItem.

    Expects the host class to provide:
        _cursor: QTextCursor
        _document: QTextDocument
        _undo_snapshot: str
        _undo_pending: bool
        _commit_undo_checkpoint(): method
        _auto_resize(): method
        update(): method
        cursor_moved: Signal
        scene(): method
    """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_char_format(self, fmt: QTextCharFormat) -> None:
        """Apply a character format to selection or cursor insertion point."""
        self._cursor.mergeCharFormat(fmt)
        self._auto_resize()
        self.update()
        self.cursor_moved.emit()

    def _push_format_command(
        self, old_html: str, new_html: str, description: str
    ) -> None:
        """Push a FormatTextCommand onto the undo stack."""
        from commands.format_text_command import FormatTextCommand
        scene = self.scene()
        if scene is None:
            return
        cmd = FormatTextCommand(self, old_html, new_html, description, scene)
        undo_stack.push(cmd)

    # ------------------------------------------------------------------
    # Bold / Italic / Underline / Strikethrough
    # ------------------------------------------------------------------

    def apply_bold(self, bold: bool) -> None:
        self._commit_undo_checkpoint()
        old_html = self._document.toHtml()
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
        self._apply_char_format(fmt)
        new_html = self._document.toHtml()
        if old_html != new_html:
            self._push_format_command(
                old_html, new_html, "Fett" if bold else "Fett aufheben")
        self._undo_snapshot = new_html
        self._undo_pending = False

    def apply_italic(self, italic: bool) -> None:
        self._commit_undo_checkpoint()
        old_html = self._document.toHtml()
        fmt = QTextCharFormat()
        fmt.setFontItalic(italic)
        self._apply_char_format(fmt)
        new_html = self._document.toHtml()
        if old_html != new_html:
            self._push_format_command(
                old_html, new_html, "Kursiv" if italic else "Kursiv aufheben")
        self._undo_snapshot = new_html
        self._undo_pending = False

    def apply_underline(self, underline: bool) -> None:
        self._commit_undo_checkpoint()
        old_html = self._document.toHtml()
        fmt = QTextCharFormat()
        fmt.setFontUnderline(underline)
        self._apply_char_format(fmt)
        new_html = self._document.toHtml()
        if old_html != new_html:
            self._push_format_command(
                old_html, new_html,
                "Unterstrichen" if underline else "Unterstrichen aufheben")
        self._undo_snapshot = new_html
        self._undo_pending = False

    def apply_strikethrough(self, strikethrough: bool) -> None:
        self._commit_undo_checkpoint()
        old_html = self._document.toHtml()
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(strikethrough)
        self._apply_char_format(fmt)
        new_html = self._document.toHtml()
        if old_html != new_html:
            self._push_format_command(
                old_html, new_html,
                "Durchgestrichen" if strikethrough else "Durchgestrichen aufheben")
        self._undo_snapshot = new_html
        self._undo_pending = False

    # ------------------------------------------------------------------
    # Font size / family (debounced via QTimer)
    # ------------------------------------------------------------------

    def apply_font_size(self, size: int) -> None:
        size = max(size, 1)  # guard against <= 0
        self._commit_undo_checkpoint()
        if not hasattr(self, '_size_timer'):
            self._size_timer = QTimer()
            self._size_timer.setSingleShot(True)
            self._size_timer.setInterval(400)
            self._size_timer.timeout.connect(self._commit_size_command)
        if not self._size_timer.isActive():
            self._size_old_html = self._undo_snapshot
        fmt = QTextCharFormat()
        fmt.setFontPointSize(float(size))
        self._apply_char_format(fmt)
        self._size_timer.start()

    def _commit_size_command(self) -> None:
        new_html = self._document.toHtml()
        old_html = getattr(self, '_size_old_html', self._undo_snapshot)
        if old_html != new_html:
            self._push_format_command(
                old_html, new_html, "Schriftgröße ändern")
        self._undo_snapshot = new_html
        self._undo_pending = False

    def apply_font_family(self, family: str) -> None:
        self._commit_undo_checkpoint()
        if not hasattr(self, '_family_timer'):
            self._family_timer = QTimer()
            self._family_timer.setSingleShot(True)
            self._family_timer.setInterval(500)
            self._family_timer.timeout.connect(self._commit_family_command)
        if not self._family_timer.isActive():
            self._family_old_html = self._undo_snapshot
        fmt = QTextCharFormat()
        fmt.setFontFamilies([family])
        self._apply_char_format(fmt)
        self._family_timer.start()

    def _commit_family_command(self) -> None:
        new_html = self._document.toHtml()
        old_html = getattr(self, '_family_old_html', self._undo_snapshot)
        if old_html != new_html:
            self._push_format_command(
                old_html, new_html, "Schriftart ändern")
        self._undo_snapshot = new_html
        self._undo_pending = False

    # ------------------------------------------------------------------
    # Color / Alignment
    # ------------------------------------------------------------------

    def apply_color(self, color: QColor) -> None:
        self._commit_undo_checkpoint()
        old_html = self._document.toHtml()
        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(color))
        self._apply_char_format(fmt)
        new_html = self._document.toHtml()
        if old_html != new_html:
            self._push_format_command(old_html, new_html, "Textfarbe ändern")
        self._undo_snapshot = new_html
        self._undo_pending = False

    def apply_alignment(self, alignment: Qt.AlignmentFlag) -> None:
        self._commit_undo_checkpoint()
        old_html = self._document.toHtml()
        block_fmt = QTextBlockFormat()
        block_fmt.setAlignment(alignment)
        self._cursor.mergeBlockFormat(block_fmt)
        self._auto_resize()
        self.update()
        self.cursor_moved.emit()
        new_html = self._document.toHtml()
        if old_html != new_html:
            self._push_format_command(old_html, new_html, "Ausrichtung ändern")
        self._undo_snapshot = new_html
        self._undo_pending = False

    # ------------------------------------------------------------------
    # Format queries
    # ------------------------------------------------------------------

    def get_current_char_format(self) -> QTextCharFormat:
        return self._cursor.charFormat()

    def get_current_block_format(self) -> QTextBlockFormat:
        return self._cursor.blockFormat()

    def apply_font_scale(self, scale_factor: float) -> None:
        """Scale all font sizes across the document proportionally with fine float precision."""
        if scale_factor <= 0.0 or abs(scale_factor - 1.0) < 0.0001:
            return

        self._document.blockSignals(True)
        try:
            default_font = self._document.defaultFont()
            old_pt = default_font.pointSizeF()
            if old_pt <= 0:
                old_pt = float(default_font.pointSize())
            new_default_pt = max(1.0, round(old_pt * scale_factor, 3))
            default_font.setPointSizeF(new_default_pt)
            default_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            default_font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            self._document.setDefaultFont(default_font)
            self._style.font_size = new_default_pt

            from PySide6.QtGui import QTextCursor
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
                            fmt.setFontPointSize(max(1.0, round(current_pt * scale_factor, 3)))
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
            self.update()
        finally:
            self._document.blockSignals(False)

