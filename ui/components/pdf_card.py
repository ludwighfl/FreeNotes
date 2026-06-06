"""Single PDF thumbnail card with lazy rendering and annotation overlay."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QObject, QRunnable
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
)


class PdfCardWorkerSignals(QObject):
    """Signals for background PDF card rendering."""
    finished = Signal(Path, Path, QImage, list, list, list, list, list, float, float, float)
    error = Signal(Path)


class PdfCardWorker(QRunnable):
    """Generates PDF card thumbnails off the main thread to prevent UI lag."""
    def __init__(self, pdf_path: Path, freenotes_path: Path | None):
        super().__init__()
        self.pdf_path = pdf_path
        self.freenotes_path = freenotes_path
        self.signals = PdfCardWorkerSignals()

    def run(self) -> None:
        import fitz
        
        try:
            doc = fitz.open(str(self.pdf_path))
            
            data = None
            if self.freenotes_path and self.freenotes_path.exists():
                data = json.loads(self.freenotes_path.read_text(encoding="utf-8"))

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
            else:
                if data:
                    page_data = data.get("pages", {}).get(str(real_page_0), {})
                    size = page_data.get("size", [595.0, 842.0])
                    page0_w = size[0] * zoom
                    h = size[1] * zoom
                max_w = page0_w
                img = QImage(int(page0_w), int(h), QImage.Format.Format_RGB888)
                img.fill(Qt.GlobalColor.white)

            doc.close()

            strokes = []
            highlights = []
            textboxes = []
            shapes = []
            images = []
            
            if data:
                page_data = data.get("pages", {}).get("0", {})
                strokes = page_data.get("strokes", [])
                highlights = page_data.get("highlights", [])
                textboxes = page_data.get("textboxes", [])
                shapes = page_data.get("shapes", [])
                images = page_data.get("images", [])

            self.signals.finished.emit(
                self.pdf_path, self.freenotes_path, img, 
                strokes, highlights, textboxes, shapes, images,
                max_w, page0_w, h
            )
        except Exception:
            self.signals.error.emit(self.pdf_path)


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

        self._shimmer = None
        if not self._rendered:
            from ui.animations.shimmer import ShimmerOverlay
            self._shimmer = ShimmerOverlay(self._thumb_label, border_radius=4)

        # Filename
        display_name = name
        if len(display_name) > 22:
            display_name = display_name[:20] + "…"
        self._name_label = QLabel(display_name)
        self._name_label.setFont(QFont("Roboto", 11, QFont.Weight.Bold))
        self._name_label.setObjectName("pdfCardName")
        self._name_label.setWordWrap(False)
        layout.addWidget(self._name_label)

        # Date
        try:
            dt = datetime.fromtimestamp(modified)
            date_str = dt.strftime("%d.%m.%Y, %H:%M")
        except Exception:
            date_str = ""
        self._date_label = QLabel(date_str)
        self._date_label.setFont(QFont("Roboto", 10))
        self._date_label.setObjectName("pdfCardDate")
        layout.addWidget(self._date_label)
        
        # Background hover fade effect (completely replaces dynamic shadow to prevent grid wiggling/jitter)
        from ui.animations.fade_hover import BackgroundFadeHoverEffect
        from core.app_settings import AppSettings
        from PySide6.QtGui import QColor
        
        is_light = AppSettings.get_theme() == "light"
        hover_color = QColor(0, 0, 0, 10) if is_light else QColor(255, 255, 255, 15)
        
        self._hover_effect = BackgroundFadeHoverEffect(
            widget=self,
            hover_color=hover_color,
            border_radius=8
        )
        
        
    def update_size(self, width: int) -> None:
        height = int(width * 1.4) # 280/200
        self.setFixedSize(width, height)
        
        # update thumbnail size
        thumb_w = width - 16
        thumb_h = int(thumb_w * (200.0 / 184.0))
        self.THUMB_W = thumb_w
        self.THUMB_H = thumb_h
        self._thumb_label.setFixedSize(thumb_w, thumb_h)
        
        if not self._thumb_label.property("placeholder") and self._rendered:
            if self._thumbnail_cache is not None and self._pdf_path:
                cached = self._thumbnail_cache.get(self._pdf_path, self.THUMB_W, self.THUMB_H)
                if cached:
                    self._thumb_label.setPixmap(cached.scaled(
                        thumb_w, thumb_h,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation))

    def update_metadata(self, name: str, modified: float) -> None:
        """Update name and modified date labels without fully rebuilding the card."""
        self._name = name
        display_name = name
        if len(display_name) > 22:
            display_name = display_name[:20] + "…"
        self._name_label.setText(display_name)
        
        self._modified = modified
        try:
            dt = datetime.fromtimestamp(modified)
            date_str = dt.strftime("%d.%m.%Y, %H:%M")
        except Exception:
            date_str = ""
        self._date_label.setText(date_str)

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
                        self._apply_pixmap(cached)
                        return

                # Spawn background worker to prevent UI lag
                from PySide6.QtCore import QThreadPool
                worker = PdfCardWorker(self._pdf_path, self._freenotes_path)
                worker.signals.finished.connect(self._on_worker_finished)
                worker.signals.error.connect(self._on_worker_error)
                QThreadPool.globalInstance().start(worker)

            except Exception:
                self._show_placeholder()
        else:
            self._show_placeholder()

    def _apply_pixmap(self, pixmap: QPixmap) -> None:
        """Apply final pixmap and stop shimmer."""
        if self._shimmer:
            self._shimmer.stop()
            self._shimmer = None
            
        self._thumb_label.setPixmap(pixmap.scaled(
            self.THUMB_W, self.THUMB_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    def _on_worker_error(self, pdf_path: Path) -> None:
        if self._pdf_path == pdf_path:
            self._show_placeholder()

    def _on_worker_finished(
        self, pdf_path: Path, freenotes_path: Path | None, img: QImage, 
        strokes: list, highlights: list, textboxes: list, shapes: list, images: list,
        max_w: float, page0_w: float, h: float
    ) -> None:
        """Called on main thread when fitz has finished generating the base image."""
        if self._pdf_path != pdf_path:
            return

        from PySide6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem
        
        try:
            pixmap = QPixmap.fromImage(img)
            
            x_off = (max_w - page0_w) / 2.0
            y_off = 20.0  # PageScene.PAGE_GAP

            # Create a lightweight, isolated scene
            scene = QGraphicsScene()
            page_item = QGraphicsPixmapItem(pixmap)
            scene.addItem(page_item)

            if strokes or highlights or textboxes or shapes or images:
                from core.freenotes_store import FreenotesStore
                from items.shape_item import ShapeItem
                from items.image_item import ImageItem
                
                for d in strokes:
                    item = FreenotesStore._deserialize_stroke(d, 0)
                    item.setPos(item.pos().x() - x_off, item.pos().y() - y_off)
                    scene.addItem(item)
                    
                for d in highlights:
                    item = FreenotesStore._deserialize_highlight(d, 0)
                    item.setPos(item.pos().x() - x_off, item.pos().y() - y_off)
                    scene.addItem(item)
                    
                for d in textboxes:
                    item = FreenotesStore._deserialize_textbox(d, 0)
                    item.setPos(item.pos().x() - x_off, item.pos().y() - y_off)
                    if hasattr(item, "_is_editing"):
                        item._is_editing = False 
                    item.clearFocus()
                    scene.addItem(item)
                    
                for d in shapes:
                    item = ShapeItem.from_dict(d)
                    item.setPos(item.pos().x() - x_off, item.pos().y() - y_off)
                    scene.addItem(item)

                for d in images:
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

            final = final_pixmap.scaled(
                400, 400,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
                
            if self._thumbnail_cache is not None and not final.isNull():
                self._thumbnail_cache.put(self._pdf_path, final)

            self._apply_pixmap(final)
            
        except Exception as e:
            print(f"Thumb render error: {e}")
            self._show_placeholder()
            


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



