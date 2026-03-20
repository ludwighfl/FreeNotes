"""Single PDF thumbnail card with lazy rendering and annotation overlay."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QFont, QPixmap, QPainter, QColor, QPen, QImage, QAction,
    QBrush, QPainterPath, QPolygonF, QContextMenuEvent,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFrame,
    QLabel,
    QMenu,
    QInputDialog,
    QMessageBox,
)


class PdfCard(QFrame):
    """Single PDF thumbnail card with lazy rendering and annotation overlay."""

    double_clicked = Signal(object)  # emits doc dict
    rename_requested = Signal(str)
    delete_requested = Signal()

    THUMB_W = 184
    THUMB_H = 200

    def __init__(
        self,
        pdf_path: Path | None,
        freenotes_path: Path | None,
        name: str,
        modified: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pdf_path = pdf_path
        self._freenotes_path = freenotes_path
        self._name = name
        self._modified = modified
        self._rendered = False
        self.setObjectName("pdfCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(200, 280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 10)
        layout.setSpacing(6)

        # Thumbnail
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(self.THUMB_W, self.THUMB_H)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setObjectName("pdfCardThumb")
        self._thumb_label.setStyleSheet(
            "background: #3a3a3a; border-radius: 4px;"
        )
        layout.addWidget(self._thumb_label)

        # Filename
        display_name = name
        if len(display_name) > 22:
            display_name = display_name[:20] + "…"
        name_label = QLabel(display_name)
        name_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        name_label.setStyleSheet("color: #ffffff;")
        name_label.setWordWrap(False)
        layout.addWidget(name_label)

        # Date
        try:
            dt = datetime.fromtimestamp(modified)
            date_str = dt.strftime("%d.%m.%Y, %H:%M")
        except Exception:
            date_str = ""
        if date_str:
            date_label = QLabel(date_str)
            date_label.setFont(QFont("Segoe UI", 10))
            date_label.setStyleSheet("color: #888888;")
            layout.addWidget(date_label)

    # ------------------------------------------------------------------
    # Lazy rendering
    # ------------------------------------------------------------------

    def render_if_needed(self) -> None:
        """Render thumbnail only when card becomes visible."""
        if self._rendered:
            return
        self._rendered = True
        if self._pdf_path and self._pdf_path.exists():
            try:
                pixmap = self._render_thumbnail_with_annotations(
                    self._pdf_path, self._freenotes_path)
                self._thumb_label.setPixmap(pixmap)
            except Exception:
                self._show_placeholder()
        else:
            self._show_placeholder()

    def _show_placeholder(self) -> None:
        """Show placeholder icon if PDF could not be loaded."""
        self._thumb_label.setText("📄")
        self._thumb_label.setStyleSheet(
            "background: #3a3a3a; border-radius: 4px; "
            "color: #888888; font-size: 40px;")

    # ------------------------------------------------------------------
    # Thumbnail with annotations
    # ------------------------------------------------------------------

    def _render_thumbnail_with_annotations(
        self, pdf_path: Path, freenotes_path: Path | None
    ) -> QPixmap:
        """Render the first PDF page and overlay annotations via QPainter."""
        import fitz
        doc = fitz.open(str(pdf_path))
        page = doc.load_page(0)
        zoom = 150.0 / 72.0
        pix = page.get_pixmap(
            matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = QImage(
            pix.samples, pix.width, pix.height, pix.stride,
            QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(img)
        pdf_w = page.rect.width
        pdf_h = page.rect.height
        doc.close()

        if freenotes_path and freenotes_path.exists():
            try:
                data = json.loads(
                    freenotes_path.read_text(encoding="utf-8"))
                sx = pixmap.width() / pdf_w
                sy = pixmap.height() / pdf_h
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                page_data = data.get("pages", {}).get("0", {})
                
                for s in page_data.get("strokes", []):
                    self._draw_stroke(painter, s, sx, sy)
                for h in page_data.get("highlights", []):
                    self._draw_highlight(painter, h, sx, sy)
                for t in page_data.get("textboxes", []):
                    self._draw_textbox(painter, t, sx, sy)
                for sh in page_data.get("shapes", []):
                    self._draw_shape(painter, sh, sx, sy)
                
                painter.end()
            except Exception:
                pass

        return pixmap.scaled(
            self.THUMB_W, self.THUMB_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)

    @staticmethod
    def _draw_stroke(painter: QPainter, d: dict, sx: float, sy: float) -> None:
        pts = d.get("points", [])
        if len(pts) < 2:
            return
        ox, oy = d.get("pos", (0, 0))
        path = QPainterPath()
        path.moveTo((pts[0][0] + ox) * sx, (pts[0][1] + oy) * sy)
        for px, py in pts[1:]:
            path.lineTo((px + ox) * sx, (py + oy) * sy)
        pen = QPen(QColor(d.get("color", "#000000")),
                   d.get("width", 2) * min(sx, sy))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    @staticmethod
    def _draw_highlight(painter: QPainter, d: dict, sx: float, sy: float) -> None:
        pts = d.get("points", [])
        if len(pts) < 2:
            return
        ox, oy = d.get("pos", (0, 0))
        xs = [(p[0] + ox) * sx for p in pts]
        ys = [(p[1] + oy) * sy for p in pts]
        rect = QRectF(min(xs), min(ys),
                       max(xs) - min(xs), max(ys) - min(ys))
        color = QColor(d.get("color", "#FFFF00"))
        color.setAlphaF(0.35)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRect(rect)

    @staticmethod
    def _draw_textbox(painter: QPainter, d: dict, sx: float, sy: float) -> None:
        rect_data = d.get("rect")
        if not rect_data:
            return
        rx, ry, rw, rh = rect_data
        ox, oy = d.get("pos", (0, 0))
        rect = QRectF((rx + ox) * sx, (ry + oy) * sy, rw * sx, rh * sy)
        from PySide6.QtGui import QTextDocument
        doc = QTextDocument()
        doc.setHtml(d.get("html", ""))
        plain = doc.toPlainText()
        font_size = max(6.0, d.get("font_size", 12) * min(sx, sy))
        painter.setPen(QColor(d.get("style_color", "#000000")))
        f = QFont(d.get("font_family", "Segoe UI"), int(font_size))
        painter.setFont(f)
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            | Qt.TextFlag.TextWordWrap,
            plain)

    @staticmethod
    def _draw_shape(painter: QPainter, d: dict, sx: float, sy: float) -> None:
        rect_data = d.get("rect")
        if not rect_data:
            return
        style = d.get("style", {})
        rx, ry, rw, rh = rect_data
        ox, oy = d.get("pos", (0, 0))
        rect = QRectF((rx + ox) * sx, (ry + oy) * sy, rw * sx, rh * sy)
        stroke_c = QColor(style.get("stroke_color", "#3B7BF5"))
        stroke_w = style.get("stroke_width", 2.0) * min(sx, sy)
        fill_c = QColor(style.get("fill_color", "#00000000"))
        pen = QPen(stroke_c, stroke_w)
        brush = QBrush(fill_c) if fill_c.alpha() > 0 else QBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen)
        painter.setBrush(brush)
        shape_type = style.get("shape_type", "rect")
        if shape_type == "ellipse":
            painter.drawEllipse(rect)
        elif shape_type == "rounded_rect":
            painter.drawRoundedRect(rect, 8, 8)
        elif shape_type in ("line", "arrow"):
            painter.drawLine(rect.topLeft(), rect.bottomRight())
        elif shape_type == "triangle":
            tri = QPolygonF([
                QPointF(rect.center().x(), rect.top()),
                QPointF(rect.left(), rect.bottom()),
                QPointF(rect.right(), rect.bottom()),
            ])
            painter.drawPolygon(tri)
        else:
            painter.drawRect(rect)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def mouseDoubleClickEvent(self, event: object) -> None:
        """Emit document data on double click."""
        self.double_clicked.emit({
            "pdf": self._pdf_path,
            "freenotes": self._freenotes_path,
            "name": self._name,
        })
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Show context menu for rename and delete."""
        menu = QMenu(self)
        menu.setObjectName("pageContextMenu")
        rename_act = QAction("Umbenennen", self)
        delete_act = QAction("Löschen", self)
        menu.addAction(rename_act)
        menu.addSeparator()
        menu.addAction(delete_act)
        rename_act.triggered.connect(self._on_rename_clicked)
        delete_act.triggered.connect(self._on_delete_clicked)
        menu.exec(event.globalPos())

    def _on_rename_clicked(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Umbenennen", "Neuer Name:", text=self._name)
        if ok and name.strip():
            self.rename_requested.emit(name.strip())

    def _on_delete_clicked(self) -> None:
        reply = QMessageBox.question(
            self, "Löschen",
            f'"{self._name}" in Papierkorb verschieben?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit()
