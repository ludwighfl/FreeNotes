"""PDF path exporter – handles rendering strokes and highlights onto PDF."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING
import fitz
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath
from core.pdf_exporter import PdfExporter

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene


class PdfPathExporter:
    """Helper class to export Strokes and Highlights to a PDF page."""

    @staticmethod
    def export_strokes(
        scene: PageScene,
        page: fitz.Page,
        page_idx: int,
        sx: float,
        sy: float,
        page_origin: QPointF,
    ) -> None:
        """Draw all StrokeItems for this page onto the PDF."""
        strokes = scene._stroke_items.get(page_idx, [])

        for stroke in strokes:
            path = stroke._path
            color = stroke._style.color
            width = stroke._style.width
            item_pos = stroke.pos()

            if path.elementCount() == 0:
                continue

            shape = page.new_shape()
            last_pt = None

            i = 0
            while i < path.elementCount():
                el = path.elementAt(i)
                # Scene coordinate = path element + item position
                scene_x = el.x + item_pos.x()
                scene_y = el.y + item_pos.y()
                pt = PdfPathExporter._scene_to_pdf(
                    scene_x, scene_y, sx, sy, page_origin
                )

                if el.type == QPainterPath.ElementType.MoveToElement:
                    last_pt = pt
                elif el.type == QPainterPath.ElementType.LineToElement:
                    if last_pt is not None:
                        shape.draw_line(last_pt, pt)
                    last_pt = pt
                elif el.type == QPainterPath.ElementType.CurveToElement:
                    # Cubic Bézier: 3 control points
                    if i + 2 < path.elementCount() and last_pt is not None:
                        el1 = path.elementAt(i + 1)
                        el2 = path.elementAt(i + 2)
                        c1 = pt  # First control point
                        c2 = PdfPathExporter._scene_to_pdf(
                            el1.x + item_pos.x(),
                            el1.y + item_pos.y(),
                            sx, sy, page_origin,
                        )
                        end = PdfPathExporter._scene_to_pdf(
                            el2.x + item_pos.x(),
                            el2.y + item_pos.y(),
                            sx, sy, page_origin,
                        )
                        shape.draw_bezier(last_pt, c1, c2, end)
                        last_pt = end
                        i += 2
                i += 1

            # Scale line width proportionally
            pdf_width = width * min(sx, sy)

            shape.finish(
                color=PdfExporter.qcolor_to_fitz(color),
                fill=None,
                width=pdf_width,
                lineCap=1,      # Round cap
                lineJoin=1,     # Round join
                closePath=False,
            )
            shape.commit()

    @staticmethod
    def export_highlights(
        scene: PageScene,
        page: fitz.Page,
        page_idx: int,
        sx: float,
        sy: float,
        page_origin: QPointF,
    ) -> None:
        """Draw all HighlightItems for this page onto the PDF."""
        highlights = scene._highlight_items.get(page_idx, [])

        for hl in highlights:
            path = hl._path
            item_pos = hl.pos()
            color = hl._style.color
            width = hl._style.width

            if path.elementCount() == 0:
                continue

            # HighlightItem is a horizontal line drawn with a thick pen
            # and round caps. Export as a filled stadium shape (rounded rect).
            path_rect = path.boundingRect()
            half_w = width / 2.0

            # Compute the full visual rectangle in PDF coordinates
            x0 = (path_rect.left() + item_pos.x() - page_origin.x()) * sx
            y0 = (path_rect.top() - half_w + item_pos.y()
                  - page_origin.y()) * sy
            x1 = (path_rect.right() + item_pos.x() - page_origin.x()) * sx
            y1 = (path_rect.bottom() + half_w + item_pos.y()
                  - page_origin.y()) * sy

            h = y1 - y0
            radius = h / 2.0
            cx_right = x1  # center of right semicircle
            cx_left = x0   # center of left semicircle
            cy = (y0 + y1) / 2.0

            # Build stadium polygon: top edge → right semicircle →
            # bottom edge → left semicircle
            arc_steps = 12  # segments per semicircle
            points = []

            # Top edge (left to right)
            points.append(fitz.Point(x0, y0))
            points.append(fitz.Point(x1, y0))

            # Right semicircle (top to bottom, clockwise)
            for j in range(1, arc_steps):
                angle = -math.pi / 2 + math.pi * j / arc_steps
                px = cx_right + radius * math.cos(angle)
                py = cy + radius * math.sin(angle)
                points.append(fitz.Point(px, py))

            # Bottom edge (right to left)
            points.append(fitz.Point(x1, y1))
            points.append(fitz.Point(x0, y1))

            # Left semicircle (bottom to top, clockwise)
            for j in range(1, arc_steps):
                angle = math.pi / 2 + math.pi * j / arc_steps
                px = cx_left + radius * math.cos(angle)
                py = cy + radius * math.sin(angle)
                points.append(fitz.Point(px, py))

            # Close the shape
            points.append(points[0])

            shape = page.new_shape()
            shape.draw_polyline(points)
            shape.finish(
                color=None,
                fill=PdfExporter.qcolor_to_fitz(color),
                fill_opacity=hl.DEFAULT_OPACITY,
                width=0,
                closePath=True,
            )
            shape.commit()

    @staticmethod
    def _scene_to_pdf(
        x: float,
        y: float,
        sx: float,
        sy: float,
        page_origin: QPointF,
    ) -> fitz.Point:
        """Convert scene coordinates to PDF page coordinates."""
        return fitz.Point(
            (x - page_origin.x()) * sx,
            (y - page_origin.y()) * sy,
        )
