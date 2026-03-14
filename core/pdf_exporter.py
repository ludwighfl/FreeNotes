"""PDF exporter – main orchestrator for rendering annotations onto a PDF."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import fitz
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

if TYPE_CHECKING:
    from ui.page_scene import PageScene


class PdfExporter:
    """Export annotations from a PageScene onto a PDF.
    
    Delegates element rendering to specialized exporters:
    - PdfPathExporter (Strokes, Highlights)
    - PdfShapeExporter (Rectangles, Ellipses, Arrows)
    - PdfTextExporter (Text boxes)
    """

    def __init__(self, scene: PageScene) -> None:
        self._scene = scene

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def export(
        self,
        doc_manager: DocumentManager,
        target_pdf: str,
        progress_callback: Callable[[int], None] | None = None,
    ) -> None:
        """Export annotations to *target_pdf*, starting from the current document state.

        Args:
            doc_manager: The active DocumentManager holding the loaded PDF.
            target_pdf: Path to write the annotated PDF.
            progress_callback: Optional callback receiving 0–100 progress.
        """
        from core.pdf_path_exporter import PdfPathExporter
        from core.pdf_shape_exporter import PdfShapeExporter
        from core.pdf_text_exporter import PdfTextExporter

        doc_bytes = doc_manager.get_document_bytes()
        if not doc_bytes:
            raise ValueError("Kein Dokument geöffnet oder Fehler beim Auslesen des PDFs.")
            
        doc = fitz.open("pdf", doc_bytes)
        total_pages = doc.page_count

        for page_idx in range(total_pages):
            page = doc[page_idx]
            sx, sy, page_origin = self._get_scale(page, page_idx)

            PdfPathExporter.export_strokes(
                self._scene, page, page_idx, sx, sy, page_origin)
            PdfPathExporter.export_highlights(
                self._scene, page, page_idx, sx, sy, page_origin)
            PdfTextExporter.export(
                self._scene, page, page_idx, sx, sy, page_origin)
            PdfShapeExporter.export(
                self._scene, page, page_idx, sx, sy, page_origin)

            if progress_callback:
                pct = int((page_idx + 1) / total_pages * 100)
                progress_callback(pct)

        doc.save(target_pdf, garbage=4, deflate=True)
        doc.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_scale(
        self, page: fitz.Page, page_idx: int
    ) -> tuple[float, float, QPointF]:
        """Return (scale_x, scale_y, page_origin) for the given page.

        page_origin is the top-left corner of the page in scene coordinates.
        Annotations in scene coords must be offset by -page_origin before
        scaling to PDF coords.
        """
        scene = self._scene

        # Get logical page size from scene
        if page_idx < len(scene._page_rects):
            page_rect = scene._page_rects[page_idx]
            scene_w = page_rect.width()
            scene_h = page_rect.height()
            page_origin = QPointF(page_rect.x(), page_rect.y())
        else:
            # Fallback: compute from DPI
            pdf_w = page.rect.width
            pdf_h = page.rect.height
            scene_w = pdf_w * 150.0 / 72.0
            scene_h = pdf_h * 150.0 / 72.0
            page_origin = QPointF(0, 0)

        pdf_w = page.rect.width
        pdf_h = page.rect.height

        sx = pdf_w / scene_w if scene_w > 0 else 1.0
        sy = pdf_h / scene_h if scene_h > 0 else 1.0
        return sx, sy, page_origin

    @staticmethod
    def qcolor_to_fitz(color: QColor) -> tuple[float, float, float]:
        """Convert QColor to fitz RGB tuple (0.0–1.0)."""
        return (color.redF(), color.greenF(), color.blueF())
