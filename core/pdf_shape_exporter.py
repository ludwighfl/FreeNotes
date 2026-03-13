"""PDF shape exporter – handles rendering geometric shapes onto PDF."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING
import fitz
from PySide6.QtCore import QPointF
from core.pdf_exporter import PdfExporter
from core.shape_style import ShapeType

if TYPE_CHECKING:
    from ui.page_scene import PageScene
    from items.shape_item import ShapeItem


class PdfShapeExporter:
    """Helper class to export ShapeItems to a PDF page."""

    @staticmethod
    def export(
        scene: PageScene,
        page: fitz.Page,
        page_idx: int,
        sx: float,
        sy: float,
        page_origin: QPointF,
    ) -> None:
        """Export all ShapeItems for this page."""
        shapes = scene._shape_items.get(page_idx, [])
        for shape_item in shapes:
            PdfShapeExporter._export_single_shape(
                page, shape_item, sx, sy, page_origin)

    @staticmethod
    def _export_single_shape(
        page: fitz.Page,
        shape_item: ShapeItem,
        sx: float,
        sy: float,
        page_origin: QPointF,
    ) -> None:
        """Export a single ShapeItem."""
        r = shape_item._rect  # local coords (0,0,w,h)
        pos = shape_item.pos()
        st = shape_item._style
        rotation = shape_item.rotation()

        # Rect in PDF coordinates
        x0 = (pos.x() - page_origin.x()) * sx
        y0 = (pos.y() - page_origin.y()) * sy
        x1 = (pos.x() + r.width() - page_origin.x()) * sx
        y1 = (pos.y() + r.height() - page_origin.y()) * sy
        fitz_rect = fitz.Rect(x0, y0, x1, y1)

        stroke_c = PdfExporter.qcolor_to_fitz(st.stroke_color)
        fill_c = None
        fill_opacity = 1.0
        if st.fill_color.alpha() > 0:
            fill_c = PdfExporter.qcolor_to_fitz(st.fill_color)
            fill_opacity = st.fill_color.alphaF()
        stroke_w = st.stroke_width * min(sx, sy)
        dashes = "[6 4] 0" if st.dash else None

        # Rotation morph around center
        morph = None
        if rotation != 0:
            cx = (x0 + x1) / 2
            cy = (y0 + y1) / 2
            center = fitz.Point(cx, cy)
            morph = (center, fitz.Matrix(rotation))

        shape = page.new_shape()

        match st.shape_type:
            case ShapeType.RECT:
                shape.draw_rect(fitz_rect)

            case ShapeType.ROUNDED_RECT:
                cr = st.corner_radius * min(sx, sy)
                points = PdfShapeExporter._rounded_rect_points(fitz_rect, cr)
                shape.draw_polyline(points)

            case ShapeType.ELLIPSE:
                shape.draw_oval(fitz_rect)

            case ShapeType.LINE:
                shape.draw_line(
                    fitz.Point(x0, y0), fitz.Point(x1, y1))

            case ShapeType.ARROW:
                PdfShapeExporter._draw_arrow_shape(
                    shape, page, fitz_rect, stroke_c, stroke_w,
                    morph, fill_opacity, dashes)
                return  # arrow handles its own finish/commit

            case ShapeType.TRIANGLE:
                top = fitz.Point((x0 + x1) / 2, y0)
                bot_l = fitz.Point(x0, y1)
                bot_r = fitz.Point(x1, y1)
                shape.draw_polyline([top, bot_l, bot_r, top])

        is_closed = st.shape_type not in {
            ShapeType.LINE, ShapeType.ARROW}

        shape.finish(
            color=stroke_c,
            fill=fill_c,
            fill_opacity=fill_opacity if fill_c else 1.0,
            width=stroke_w,
            dashes=dashes,
            morph=morph,
            closePath=is_closed,
            lineCap=1,
            lineJoin=1,
        )
        shape.commit()

    @staticmethod
    def _draw_arrow_shape(
        shape: fitz.Shape,
        page: fitz.Page,
        rect: fitz.Rect,
        color: tuple,
        width: float,
        morph,
        fill_opacity: float,
        dashes: str | None,
    ) -> None:
        """Draw an arrow: line + filled arrowhead."""
        p1 = fitz.Point(rect.x0, rect.y0)
        p2 = fitz.Point(rect.x1, rect.y1)

        dx = p2.x - p1.x
        dy = p2.y - p1.y
        length = math.hypot(dx, dy)
        if length < 1.0:
            return

        ux, uy = dx / length, dy / length
        # Scale minimums from scene pixels to PDF points
        scale = min(1.0, width / 2.0) if width > 0 else 0.5
        head_len = min(length * 0.4, max(6.0, width * 3))
        head_width = min(length * 0.2, max(3.0, width * 1.5))

        lx = -uy * head_width
        ly = ux * head_width
        base = fitz.Point(p2.x - ux * head_len, p2.y - uy * head_len)
        left = fitz.Point(base.x + lx, base.y + ly)
        right = fitz.Point(base.x - lx, base.y - ly)

        # Line (shaft)
        shape.draw_line(p1, base)
        shape.finish(
            color=color, fill=None, width=width,
            lineCap=1, lineJoin=1, morph=morph,
            dashes=dashes, closePath=False,
        )

        # Arrowhead (filled triangle)
        shape.draw_polyline([p2, left, right, p2])
        shape.finish(
            color=color, fill=color, width=0,
            closePath=True, morph=morph,
        )
        shape.commit()

    @staticmethod
    def _rounded_rect_points(
        rect: fitz.Rect, radius: float
    ) -> list[fitz.Point]:
        """Build a polyline approximation of a rounded rectangle."""
        x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
        r = min(radius, (x1 - x0) / 2, (y1 - y0) / 2)
        arc_steps = 8
        points = []

        # Top edge
        points.append(fitz.Point(x0 + r, y0))
        points.append(fitz.Point(x1 - r, y0))
        # Top-right corner
        for j in range(1, arc_steps + 1):
            angle = -math.pi / 2 + (math.pi / 2) * j / arc_steps
            points.append(fitz.Point(
                x1 - r + r * math.cos(angle),
                y0 + r + r * math.sin(angle),
            ))
        # Right edge
        points.append(fitz.Point(x1, y1 - r))
        # Bottom-right corner
        for j in range(1, arc_steps + 1):
            angle = 0 + (math.pi / 2) * j / arc_steps
            points.append(fitz.Point(
                x1 - r + r * math.cos(angle),
                y1 - r + r * math.sin(angle),
            ))
        # Bottom edge
        points.append(fitz.Point(x0 + r, y1))
        # Bottom-left corner
        for j in range(1, arc_steps + 1):
            angle = math.pi / 2 + (math.pi / 2) * j / arc_steps
            points.append(fitz.Point(
                x0 + r + r * math.cos(angle),
                y1 - r + r * math.sin(angle),
            ))
        # Left edge
        points.append(fitz.Point(x0, y0 + r))
        # Top-left corner
        for j in range(1, arc_steps + 1):
            angle = math.pi + (math.pi / 2) * j / arc_steps
            points.append(fitz.Point(
                x0 + r + r * math.cos(angle),
                y0 + r + r * math.sin(angle),
            ))
        # Close
        points.append(points[0])
        return points
