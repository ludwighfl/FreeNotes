"""PDF image exporter – handles rendering image annotations onto PDF."""

from __future__ import annotations

import io
import math
from typing import TYPE_CHECKING

import fitz
from PySide6.QtCore import QPointF

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene
    from items.image_item import ImageItem


class PdfImageExporter:
    """Helper class to export ImageItems to a PDF page."""

    @staticmethod
    def export(
        scene: PageScene,
        page: fitz.Page,
        page_idx: int,
        sx: float,
        sy: float,
        page_origin: QPointF,
    ) -> None:
        """Export all ImageItems for this page."""
        images = scene._image_items.get(page_idx, [])
        for image_item in images:
            PdfImageExporter._export_single_image(
                page, image_item, sx, sy, page_origin)

    @staticmethod
    def _export_single_image(
        page: fitz.Page,
        image_item: ImageItem,
        sx: float,
        sy: float,
        page_origin: QPointF,
    ) -> None:
        """Export a single ImageItem."""
        r = image_item._rect  # local coords (0,0,w,h)
        pos = image_item.pos()
        rotation = image_item.rotation()

        # Rect in PDF coordinates
        x0 = (pos.x() - page_origin.x()) * sx
        y0 = (pos.y() - page_origin.y()) * sy
        x1 = (pos.x() + r.width() - page_origin.x()) * sx
        y1 = (pos.y() + r.height() - page_origin.y()) * sy
        fitz_rect = fitz.Rect(x0, y0, x1, y1)

        # Image data as bytes stream
        image_stream = image_item._image_bytes

        # Rotation morph around center
        rotate = 0
        if rotation != 0:
            # fitz.insert_image supports rotation parameter directly
            rotate = int(rotation) % 360

        try:
            page.insert_image(
                fitz_rect,
                stream=image_stream,
                rotate=rotate,
            )
        except Exception:
            # Fallback: try saving as PNG first
            try:
                from PySide6.QtCore import QByteArray, QBuffer, QIODevice
                qba = QByteArray()
                qbuf = QBuffer(qba)
                qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
                image_item._pixmap.toImage().save(qbuf, "PNG")
                qbuf.close()
                png_bytes = bytes(qba.data())
                page.insert_image(
                    fitz_rect,
                    stream=png_bytes,
                    rotate=rotate,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "Image export failed: %s", e)
