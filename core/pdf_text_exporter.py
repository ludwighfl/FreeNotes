"""PDF text exporter – handles rendering rich text boxes onto PDF."""

from __future__ import annotations

from typing import TYPE_CHECKING
import fitz
import logging
from PySide6.QtCore import QPointF

logger = logging.getLogger(__name__)
from core.pdf_exporter import PdfExporter

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene
    from items.text_box_item import TextBoxItem


class PdfTextExporter:
    """Helper class to export TextBoxItems to a PDF page."""

    @staticmethod
    def export(
        scene: PageScene,
        page: fitz.Page,
        page_idx: int,
        sx: float,
        sy: float,
        page_origin: QPointF,
    ) -> None:
        """Export all TextBoxItems for this page."""
        boxes = scene._text_box_items.get(page_idx, [])
        for box in boxes:
            PdfTextExporter._export_single_textbox(
                page, box, sx, sy, page_origin)

    @staticmethod
    def _export_single_textbox(
        page: fitz.Page,
        box: TextBoxItem,
        sx: float,
        sy: float,
        page_origin: QPointF,
    ) -> None:
        """Export a single TextBoxItem."""
        from PySide6.QtGui import QColor as _QColor

        doc_qt = box._document
        item_pos = box.pos()
        box_rect = box._rect  # local coords (0, 0, w, h)
        rotation = box.rotation()
        padding = box.PADDING

        # Box rect in PDF coords
        x0 = (item_pos.x() - page_origin.x()) * sx
        y0 = (item_pos.y() - page_origin.y()) * sy
        x1 = (item_pos.x() + box_rect.width() - page_origin.x()) * sx
        y1 = (item_pos.y() + box_rect.height() - page_origin.y()) * sy
        pad_x = padding * sx
        pad_y = padding * sy

        # Rotation morph (around box center)
        morph = None
        if rotation != 0:
            cx = (x0 + x1) / 2
            cy = (y0 + y1) / 2
            center = fitz.Point(cx, cy)
            morph = (center, fitz.Matrix(rotation))

        # Force QTextDocument to calculate its layout (critical for headless export)
        doc_qt.documentLayout().documentSize()

        # Iterate QTextDocument blocks
        block = doc_qt.begin()
        y_cursor = y0 + pad_y

        while block.isValid():
            block_layout = block.layout()
            if block_layout is None:
                block = block.next()
                continue

            # Process each line in the block layout
            layout_pos = block_layout.position()
            for line_idx in range(block_layout.lineCount()):
                line = block_layout.lineAt(line_idx)
                line_rect = line.rect()

                # Line position in PDF coords (layout pos + line rect pos)
                doc_x = layout_pos.x() + line_rect.x()
                doc_y = layout_pos.y() + line_rect.y()
                line_x = x0 + pad_x + doc_x * sx
                line_y = y0 + pad_y + doc_y * sy

                # Get text range for this line
                line_start = line.textStart()
                line_length = line.textLength()

                # Iterate fragments that intersect this line
                it = block.begin()
                while not it.atEnd():
                    fragment = it.fragment()
                    if fragment.isValid():
                        frag_start = fragment.position() - block.position()
                        frag_end = frag_start + fragment.length()

                        # Check overlap with this line
                        overlap_start = max(frag_start, line_start)
                        overlap_end = min(frag_end, line_start + line_length)

                        if overlap_start < overlap_end:
                            text = fragment.text()[overlap_start - frag_start:
                                                   overlap_end - frag_start]
                            if text.strip() or text:
                                char_fmt = fragment.charFormat()

                                # Font size
                                font_size = char_fmt.fontPointSize()
                                if font_size <= 0:
                                    font_size = doc_qt.defaultFont().pointSizeF()
                                if font_size <= 0:
                                    font_size = 12.0
                                # Scale font: Qt renders at screen DPI, scene at 150 DPI
                                from PySide6.QtWidgets import QApplication
                                screen = QApplication.instance().primaryScreen()
                                screen_dpi = screen.logicalDotsPerInch() if screen else 96
                                font_size_pdf = font_size * screen_dpi / 150.0

                                # Bold / Italic
                                bold = char_fmt.fontWeight() >= 700
                                italic = char_fmt.fontItalic()

                                # Color
                                fg_color = char_fmt.foreground().color()
                                if not fg_color.isValid():
                                    fg_color = _QColor("#000000")

                                # Font family
                                families = char_fmt.fontFamilies()
                                if isinstance(families, list) and families:
                                    family = families[0]
                                elif isinstance(families, str) and families:
                                    family = families
                                else:
                                    family = doc_qt.defaultFont().family()

                                fitz_font = PdfTextExporter._map_font(
                                    family or "helv", bold, italic)

                                # Precise x position via cursorToX
                                try:
                                    frag_x = line.cursorToX(overlap_start)[0]
                                except Exception as e:
                                    logger.warning("Failed to calculate cursor position: %s", e)
                                    frag_x = 0
                                x_in_line = x0 + pad_x + \
                                    (layout_pos.x() + frag_x) * sx

                                # Baseline = line top + ascent
                                ascent_pdf = line.ascent() * sy
                                insert_y = line_y + ascent_pdf

                                try:
                                    page.insert_text(
                                        point=fitz.Point(x_in_line, insert_y),
                                        text=text,
                                        fontsize=font_size_pdf,
                                        fontname=fitz_font,
                                        color=PdfExporter.qcolor_to_fitz(
                                            fg_color),
                                        morph=morph,
                                    )
                                except Exception as e:
                                    logger.warning("Failed to insert text %r: %s", text, e)

                    it.__next__()

            block = block.next()

    @staticmethod
    def _map_font(family: str, bold: bool, italic: bool) -> str:
        """Map a Qt font family to a fitz built-in font name."""
        fl = family.lower()

        if any(k in fl for k in ("courier", "mono", "consolas")):
            if bold and italic:
                return "cobi"
            if bold:
                return "cobo"
            if italic:
                return "coit"
            return "cour"

        if any(k in fl for k in ("times", "serif", "georgia")):
            if bold and italic:
                return "tibi"
            if bold:
                return "tibo"
            if italic:
                return "tiit"
            return "tiro"

        # Default: Helvetica
        if bold and italic:
            return "hebi"
        if bold:
            return "hebo"
        if italic:
            return "heit"
        return "helv"
