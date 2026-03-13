from PySide6.QtCore import Qt, Signal, QTimer, QRectF, QMimeData, QPoint
from PySide6.QtGui import (
    QPixmap, QPainter, QFont, QColor, QPen, QBrush, QDrag,
    QMouseEvent,
)
from PySide6.QtWidgets import (
    QScrollArea,
    QWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
)

from core.document_manager import DocumentManager
from app.app_state import AppState

# TYPE_CHECKING import to avoid circular dependency problems on init
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.page_scene import PageScene
    from ui.viewer_window import ViewerWindow


class ThumbnailCard(QFrame):
    """Single thumbnail card: page image + page number badge."""

    clicked = Signal(int)

    THUMB_WIDTH: int = 160
    BADGE_COLOR: str = "#3B7BF5"
    ACTIVE_BORDER_COLOR: str = "#3B7BF5"

    def __init__(self, page_index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page_index: int = page_index
        self._is_active: bool = False
        self._thumb_label: QLabel = QLabel(self)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        layout.addWidget(self._thumb_label)

        self.setObjectName("thumbnailCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        """Set the thumbnail pixmap, scaled to THUMB_WIDTH with page badge."""
        if pixmap.isNull():
            return
        # Account for HiDPI: scale to logical width × devicePixelRatio
        dpr = pixmap.devicePixelRatio()
        physical_width = int(self.THUMB_WIDTH * dpr)
        scaled = pixmap.scaledToWidth(
            physical_width, Qt.TransformationMode.SmoothTransformation
        )
        scaled.setDevicePixelRatio(dpr)
        self._scaled_pixmap = scaled  # keep for badge re-render
        self._render_badge()

    def update_page_number(self, new_index: int) -> None:
        """Update the page index and re-render the badge."""
        self._page_index = new_index
        self._render_badge()

    def _render_badge(self) -> None:
        """Draw the page number badge on the stored scaled pixmap."""
        scaled = getattr(self, '_scaled_pixmap', None)
        if scaled is None:
            return
        dpr = scaled.devicePixelRatio()

        # Draw page number badge (in physical pixel space)
        badge_pixmap = QPixmap(scaled.size())
        badge_pixmap.setDevicePixelRatio(dpr)
        badge_pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(badge_pixmap)
        painter.drawPixmap(0, 0, scaled)

        # Badge background
        badge_text = str(self._page_index + 1)
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        text_width = fm.horizontalAdvance(badge_text) + 12
        text_height = fm.height() + 6
        badge_x = scaled.width() - text_width - 6
        badge_y = scaled.height() - text_height - 6
        painter.setBrush(QBrush(QColor(self.BADGE_COLOR)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge_x, badge_y, text_width, text_height, 4, 4)

        # Badge text
        painter.setPen(QColor("#ffffff"))
        painter.drawText(
            badge_x, badge_y, text_width, text_height,
            Qt.AlignmentFlag.AlignCenter, badge_text,
        )
        painter.end()

        self._thumb_label.setPixmap(badge_pixmap)

    def set_active(self, active: bool) -> None:
        """Set whether this card is the active page."""
        if self._is_active != active:
            self._is_active = active
            self._update_style()

    def _update_style(self) -> None:
        if self._is_active:
            self.setStyleSheet(
                f"#thumbnailCard {{ border: 2px solid {self.ACTIVE_BORDER_COLOR}; "
                f"border-radius: 4px; background: #2d2d2d; }}"
            )
        else:
            self.setStyleSheet(
                "#thumbnailCard { border: 2px solid transparent; "
                "border-radius: 4px; background: #242424; }"
            )

    # --- Drag support ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        self.clicked.emit(self._page_index)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        start = getattr(self, '_drag_start_pos', None)
        if start is None:
            return
        if (event.pos() - start).manhattanLength() < 20:
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-freenotes-page",
                     str(self._page_index).encode())
        drag.setMimeData(mime)

        # Semi-transparent preview
        thumb = self._thumb_label.pixmap()
        if thumb and not thumb.isNull():
            preview = QPixmap(thumb.size())
            preview.setDevicePixelRatio(thumb.devicePixelRatio())
            preview.fill(Qt.GlobalColor.transparent)
            p = QPainter(preview)
            p.setOpacity(0.6)
            p.drawPixmap(0, 0, thumb)
            p.end()
            drag.setPixmap(preview)

        drag.exec(Qt.DropAction.MoveAction)


class SidebarWidget(QScrollArea):
    """Scrollable sidebar with lazy-loaded page thumbnails.

    Only visible thumbnails + 2 buffer pages above/below are rendered
    at dpi=72 for performance.
    """

    page_clicked = Signal(int)

    THUMBNAIL_DPI: int = 72

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._doc_manager: DocumentManager | None = None
        self._scene: 'PageScene' | None = None
        self._viewer: 'ViewerWindow | None' = None
        self._cards: list[ThumbnailCard] = []
        self._loaded_pages: set[int] = set()
        self._active_index: int = -1
        self._app_state: AppState = AppState()
        self._drop_indicator_index: int = -1

        # Container widget
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(self._container)

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(180)
        self.setMaximumWidth(210)
        self.setObjectName("sidebarWidget")
        self.setAcceptDrops(True)

        # Lazy load timer
        self._lazy_timer = QTimer(self)
        self._lazy_timer.setInterval(100)
        self._lazy_timer.setSingleShot(True)
        self._lazy_timer.timeout.connect(self._load_visible_thumbnails)
        self.verticalScrollBar().valueChanged.connect(
            lambda: self._lazy_timer.start()
        )

        # Listen for page changes
        self._app_state.page_changed.connect(self.set_active_page)

    def load_document(self, doc_manager: DocumentManager, scene: 'PageScene') -> None:
        """Create thumbnail cards for all pages in the document."""
        if self._scene is not None:
            try:
                self._scene.changed.disconnect(self._on_scene_changed)
            except RuntimeError:
                pass

        self._doc_manager = doc_manager
        self._scene = scene
        self._scene.changed.connect(self._on_scene_changed)

        self._loaded_pages.clear()
        self._active_index = -1

        for card in self._cards:
            card.deleteLater()
        self._cards.clear()

        page_count = doc_manager.get_page_count()
        for i in range(page_count):
            card = ThumbnailCard(i)
            card.clicked.connect(self._on_card_clicked)
            self._layout.addWidget(card)
            self._cards.append(card)

        if page_count > 0:
            self.set_active_page(0)

        QTimer.singleShot(50, self._load_visible_thumbnails)

    def set_viewer(self, viewer: 'ViewerWindow') -> None:
        """Set viewer reference for reorder command."""
        self._viewer = viewer

    # ------------------------------------------------------------------
    # Drag & drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat("application/x-freenotes-page"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if not event.mimeData().hasFormat("application/x-freenotes-page"):
            event.ignore()
            return
        event.acceptProposedAction()
        # Calculate drop position
        drop_idx = self._get_drop_index(event.position().toPoint())
        if drop_idx != self._drop_indicator_index:
            self._drop_indicator_index = drop_idx
            self._container.update()

    def dragLeaveEvent(self, event) -> None:
        self._drop_indicator_index = -1
        self._container.update()

    def dropEvent(self, event) -> None:
        self._drop_indicator_index = -1
        self._container.update()

        if not event.mimeData().hasFormat("application/x-freenotes-page"):
            event.ignore()
            return

        data = event.mimeData().data("application/x-freenotes-page")
        source_page = int(bytes(data).decode())
        target_idx = self._get_drop_index(event.position().toPoint())

        # Build current order (what original page each position holds)
        current_order = [card._page_index for card in self._cards]

        # Find source position in current layout
        source_pos = None
        for i, orig_idx in enumerate(current_order):
            if orig_idx == source_page:
                source_pos = i
                break
        if source_pos is None:
            return

        # No change
        if target_idx == source_pos or target_idx == source_pos + 1:
            return

        # Build new order
        new_order = list(current_order)
        moved = new_order.pop(source_pos)
        insert_at = target_idx if target_idx < source_pos else target_idx - 1
        insert_at = max(0, min(insert_at, len(new_order)))
        new_order.insert(insert_at, moved)

        if new_order == current_order:
            return

        # Push undo command
        from commands.reorder_pages_command import ReorderPagesCommand
        from core import undo_stack
        cmd = ReorderPagesCommand(
            old_order=current_order,
            new_order=new_order,
            scene=self._scene,
            doc_manager=self._doc_manager,
            sidebar=self,
        )
        undo_stack.push(cmd)

        # Apply immediately (first redo is skipped)
        self._scene.reorder_annotations(new_order)
        self._doc_manager.reorder_pages(new_order)
        self._scene.rebuild_after_reorder(self._doc_manager)
        self.refresh_order(new_order)

        event.acceptProposedAction()

    def _get_drop_index(self, pos: QPoint) -> int:
        """Return the index where a drop at pos should insert."""
        container_pos = self._container.mapFrom(self.viewport(), pos)
        for i, card in enumerate(self._cards):
            card_rect = card.geometry()
            mid_y = card_rect.y() + card_rect.height() // 2
            if container_pos.y() < mid_y:
                return i
        return len(self._cards)

    def refresh_order(self, new_order: list[int]) -> None:
        """Reorder cards to match new_order and update page numbers.

        new_order[new_pos] = old_page_index.
        """
        # Map original page index → card
        idx_to_card: dict[int, ThumbnailCard] = {
            card._page_index: card for card in self._cards
        }

        # Remove all cards from layout (without deleting)
        for card in self._cards:
            self._layout.removeWidget(card)

        # Re-add in new order
        new_cards = []
        for new_pos, old_idx in enumerate(new_order):
            card = idx_to_card.get(old_idx)
            if card:
                card.update_page_number(new_pos)
                self._layout.addWidget(card)
                new_cards.append(card)

        self._cards = new_cards
        self._loaded_pages.clear()
        QTimer.singleShot(50, self._load_visible_thumbnails)

    def set_active_page(self, page_index: int) -> None:
        """Highlight the given page in the sidebar.

        Args:
            page_index: Zero-based page index.
        """
        if self._active_index == page_index:
            return
        if 0 <= self._active_index < len(self._cards):
            self._cards[self._active_index].set_active(False)
        if 0 <= page_index < len(self._cards):
            self._cards[page_index].set_active(True)
            # Ensure visible
            self.ensureWidgetVisible(self._cards[page_index], 50, 50)
        self._active_index = page_index

    def _on_card_clicked(self, page_index: int) -> None:
        self.page_clicked.emit(page_index)

    def _on_scene_changed(self, rects: list) -> None:
        """Invalidate thumbnails that overlap with the changed area."""
        if self._scene is None or not self._cards:
            return

        for rect in rects:
            # Find which page this rect belongs to
            page_index = self._scene.get_page_index_at(rect.center())
            if page_index != -1 and page_index in self._loaded_pages:
                self._loaded_pages.remove(page_index)
                
        # Trigger lazy load to re-render invalidated visible pages
        self._lazy_timer.start()

    def _load_visible_thumbnails(self) -> None:
        """Load thumbnails for visible cards + 2 buffer pages."""
        if self._doc_manager is None or not self._cards:
            return

        viewport_rect = self.viewport().rect()
        buffer = 2

        first_visible = -1
        last_visible = -1

        for i, card in enumerate(self._cards):
            card_pos = card.mapTo(self._container, card.rect().topLeft())
            container_pos = self._container.mapTo(self.viewport(), card_pos)
            if viewport_rect.intersects(
                card.rect().translated(container_pos)
            ):
                if first_visible == -1:
                    first_visible = i
                last_visible = i

        if first_visible == -1:
            first_visible = 0
            last_visible = min(4, len(self._cards) - 1)

        # Gather items to temporarily hide from the thumbnail
        ephemeral_items = self._scene.get_ephemeral_items()
        for item in ephemeral_items:
            item.hide()
            
        # Tell items that draw their own selection borders to skip drawing
        # them during this render pass.
        self._scene._is_rendering_thumbnail = True

        start = max(0, first_visible - buffer)
        end = min(len(self._cards) - 1, last_visible + buffer)

        for i in range(start, end + 1):
            if i not in self._loaded_pages:
                # Render the scene portion for this page
                page_rect = self._scene.get_page_rect(i)
                if not page_rect.isEmpty():
                    # Calculate physical target size at THUMBNAIL_DPI
                    logical_w = page_rect.width()
                    logical_h = page_rect.height()
                    dpr = self.devicePixelRatioF()
                    
                    target_w = int(logical_w * (self.THUMBNAIL_DPI / 72.0) * dpr)
                    target_h = int(logical_h * (self.THUMBNAIL_DPI / 72.0) * dpr)
                    
                    pixmap = QPixmap(target_w, target_h)
                    pixmap.setDevicePixelRatio(dpr)
                    pixmap.fill(Qt.GlobalColor.white)
                    
                    painter = QPainter(pixmap)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                    
                    # Target rect in logical coordinates (since QPainter respects devicePixelRatio)
                    target_rect = QRectF(0, 0, logical_w * (self.THUMBNAIL_DPI / 72.0), logical_h * (self.THUMBNAIL_DPI / 72.0))
                    
                    self._scene.render(painter, target_rect, page_rect)
                    painter.end()
                    
                    self._cards[i].set_thumbnail(pixmap)
                
                self._loaded_pages.add(i)

        # Restore original visibility
        for item in ephemeral_items:
            item.show()
            
        self._scene._is_rendering_thumbnail = False
