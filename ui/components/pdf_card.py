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
        thumbnail_cache: 'ThumbnailCache' | None = None,
    ) -> None:
        super().__init__(parent)
        self._pdf_path = pdf_path
        self._freenotes_path = freenotes_path
        self._name = name
        self._modified = modified
        self._rendered = False
        self._thumbnail_cache = thumbnail_cache
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
        layout.addWidget(self._thumb_label)

        # Filename
        display_name = name
        if len(display_name) > 22:
            display_name = display_name[:20] + "…"
        name_label = QLabel(display_name)
        name_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        name_label.setObjectName("pdfCardName")
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
            date_label.setObjectName("pdfCardDate")
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
                if self._thumbnail_cache is not None:
                    cached = self._thumbnail_cache.get(self._pdf_path, self.THUMB_W, self.THUMB_H)
                    if cached:
                        self._thumb_label.setPixmap(cached)
                        return

                pixmap = self._render_thumbnail_with_annotations(
                    self._pdf_path, self._freenotes_path)
                
                if self._thumbnail_cache is not None and not pixmap.isNull():
                    self._thumbnail_cache.put(self._pdf_path, pixmap)

                self._thumb_label.setPixmap(pixmap)
            except Exception:
                self._show_placeholder()
        else:
            self._show_placeholder()

    def _show_placeholder(self) -> None:
        """Show placeholder icon if PDF could not be loaded."""
        self._thumb_label.setText("📄")
        self._thumb_label.setProperty("placeholder", True)
        self._thumb_label.style().unpolish(self._thumb_label)
        self._thumb_label.style().polish(self._thumb_label)

    # ------------------------------------------------------------------
    # Thumbnail with annotations
    # ------------------------------------------------------------------

    def _render_thumbnail_with_annotations(
        self, pdf_path: Path, freenotes_path: Path | None
    ) -> QPixmap:
        """Render the first PDF page and overlay annotations efficiently."""
        import fitz
        from PySide6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem
        import json

        try:
            doc = fitz.open(str(pdf_path))
            
            data = None
            if freenotes_path and freenotes_path.exists():
                data = json.loads(freenotes_path.read_text(encoding="utf-8"))

            zoom = 150.0 / 72.0
            page0_w = 595.0 * zoom
            h = 842.0 * zoom
            max_w = 0.0

            real_page_0 = 0
            is_blank = False

            if data:
                page_map = data.get("page_map", [])
                if page_map and isinstance(page_map, list):
                    if page_map[0] == -1:
                        is_blank = True
                    elif 0 <= page_map[0] < doc.page_count:
                        real_page_0 = page_map[0]

            if not is_blank:
                page = doc.load_page(real_page_0)
                page0_w = page.rect.width * zoom
                h = page.rect.height * zoom
                
                # Fast max_w calculation: check up to max 50 pages to avoid stutter
                max_w = page0_w
                limit = min(50, doc.page_count)
                for i in range(limit):
                    w = doc[i].rect.width * zoom
                    if w > max_w:
                        max_w = w

                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                img = QImage(
                    pix.samples, pix.width, pix.height, pix.stride,
                    QImage.Format.Format_RGB888).copy()
                pixmap = QPixmap.fromImage(img)
            else:
                max_w = page0_w
                pixmap = QPixmap(int(page0_w), int(h))
                pixmap.fill(Qt.GlobalColor.white)

            doc.close()

            x_off = (max_w - page0_w) / 2.0
            y_off = 20.0  # PageScene.PAGE_GAP

            # Create a lightweight, isolated scene
            scene = QGraphicsScene()
            page_item = QGraphicsPixmapItem(pixmap)
            scene.addItem(page_item)

            if data:
                from core.freenotes_store import FreenotesStore
                from items.shape_item import ShapeItem
                from items.image_item import ImageItem
                
                page_data = data.get("pages", {}).get("0", {})
                
                for d in page_data.get("strokes", []):
                    item = FreenotesStore._deserialize_stroke(d, 0)
                    item.setPos(item.pos().x() - x_off, item.pos().y() - y_off)
                    scene.addItem(item)
                    
                for d in page_data.get("highlights", []):
                    item = FreenotesStore._deserialize_highlight(d, 0)
                    item.setPos(item.pos().x() - x_off, item.pos().y() - y_off)
                    scene.addItem(item)
                    
                for d in page_data.get("textboxes", []):
                    item = FreenotesStore._deserialize_textbox(d, 0)
                    item.setPos(item.pos().x() - x_off, item.pos().y() - y_off)
                    if hasattr(item, "_is_editing"):
                        item._is_editing = False 
                    item.clearFocus()
                    scene.addItem(item)
                    
                for d in page_data.get("shapes", []):
                    item = ShapeItem.from_dict(d)
                    item.setPos(item.pos().x() - x_off, item.pos().y() - y_off)
                    scene.addItem(item)

                for d in page_data.get("images", []):
                    item = ImageItem.from_dict(d)
                    item.setPos(item.pos().x() - x_off, item.pos().y() - y_off)
                    scene.addItem(item)

            # Render scene seamlessly
            final_pixmap = QPixmap(int(page0_w), int(h))
            final_pixmap.fill(Qt.GlobalColor.white)
            painter = QPainter(final_pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            scene.render(painter, QRectF(0, 0, page0_w, h), QRectF(0, 0, page0_w, h))
            painter.end()

            scene.clear()

            return final_pixmap.scaled(
                self.THUMB_W, self.THUMB_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)

        except Exception as e:
            print(f"Thumb render error: {e}")
            return QPixmap()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: object) -> None:
        """Handle single clicks for selection."""
        # Check if click was on the checkbox (if visible)
        if hasattr(self, "_checkbox") and self._checkbox.isVisible() and self._checkbox.geometry().contains(event.pos()):
            # Clicked checkbox directly
            from ui.windows.manager_view import ManagerView
            parent = self.parent()
            while parent and not isinstance(parent, ManagerView):
                parent = parent.parent()
            if parent:
                parent.handle_card_click(self)
        else:
            # Emulation of a signal that can be caught by manager view
            # By passing up the chain
            from ui.windows.manager_view import ManagerView
            parent = self.parent()
            while parent and not isinstance(parent, ManagerView):
                parent = parent.parent()
            if parent:
                parent.handle_card_click(self)
                
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: object) -> None:
        """Emit document data on double click."""
        self.double_clicked.emit(self.get_doc_data())
        super().mouseDoubleClickEvent(event)

    def get_doc_data(self) -> dict:
        parent_folder = None
        if self._pdf_path and self._pdf_path.exists():
            parent_folder = self._pdf_path.parent
        elif self._freenotes_path and self._freenotes_path.exists():
            parent_folder = self._freenotes_path.parent
            
        return {
            "pdf": self._pdf_path,
            "freenotes": self._freenotes_path,
            "name": self._name,
            "folder": parent_folder,
        }

    # ------------------------------------------------------------------
    # Selection State
    # ------------------------------------------------------------------

    def set_selected(self, selected: bool) -> None:
        """Update selection visuals."""
        from ui.components.icon_factory import IconFactory
        
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

        if selected:
            if hasattr(self, "_checkbox") and self._checkbox.isVisible():
                self._checkbox.setPixmap(IconFactory.create_pixmap("check_square", "#3B7BF5", 20))
        else:
            if hasattr(self, "_checkbox") and self._checkbox.isVisible():
                self._checkbox.setPixmap(IconFactory.create_pixmap("square", "#666666", 20))

    def set_checkbox_visible(self, visible: bool) -> None:
        from ui.components.icon_factory import IconFactory
        if not hasattr(self, "_checkbox"):
            self._checkbox = QLabel(self)
            self._checkbox.setFixedSize(24, 24)
            self._checkbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._checkbox.move(12, 12)
            
        self._checkbox.setVisible(visible)
        if visible:
            # Set unselected state by default
            self._checkbox.setPixmap(IconFactory.create_pixmap("square", "#666666", 20))
