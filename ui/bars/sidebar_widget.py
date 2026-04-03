from PySide6.QtCore import Qt, Signal, QTimer, QPoint
from PySide6.QtGui import (
    QPixmap, QImage, QPainter, QContextMenuEvent, QAction,
)
from PySide6.QtWidgets import (
    QScrollArea,
    QWidget,
    QVBoxLayout,
    QMenu,
)

from core.document_manager import DocumentManager
from core.thumbnail_worker import ThumbnailWorker
from ui.components.thumbnail_card import ThumbnailCard
from app.app_state import AppState
from PySide6.QtCore import QRectF

# TYPE_CHECKING import to avoid circular dependency problems on init
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene
    from ui.windows.viewer_window import ViewerWindow


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
        # Background rendering thread
        self._thumb_worker: ThumbnailWorker | None = None
        self._thumb_generation_id: int = 0
        self._zombie_workers: set['ThumbnailWorker'] = set()
        self._queued_pages: set[int] = set()
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

        from ui.animations import DragReorderController
        self._drag_ctrl = DragReorderController(
            sidebar=self,
            get_cards=lambda: self._cards,
            get_spacing=lambda: self._layout.spacing(),
            on_reorder=self._on_drag_reorder,
            parent=self,
        )

    def clear(self) -> None:
        """Instantly wipe all thumbnails (prevents flashing old data during transitions)."""
        self._loaded_pages.clear()
        self._queued_pages.clear()
        self._active_index = -1

        if self._thumb_worker is not None:
            worker_ref = self._thumb_worker
            self._thumb_worker = None
            try:
                worker_ref.cancel()
                worker_ref.wait()
            except RuntimeError:
                pass

        self._thumb_generation_id += 1

        for card in self._cards:
            self._layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

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
        self._queued_pages.clear()
        self._active_index = -1

        if self._thumb_worker is not None:
            worker_ref = self._thumb_worker
            self._thumb_worker = None
            try:
                worker_ref.cancel()
                worker_ref.wait()
            except RuntimeError:
                pass

        self._thumb_generation_id += 1

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

    def _on_drag_reorder(self, new_order: list[int]) -> None:
        """Called by DragReorderController when a valid drag-drop reordering finishes."""
        
        # PREVENT C++ SEGFAULT: Cancel background renders BEFORE changing scene items
        if self._thumb_worker is not None:
            worker_ref = self._thumb_worker
            self._thumb_worker = None
            try:
                worker_ref.cancel()
                worker_ref.wait()
            except RuntimeError:
                pass
        self._thumb_generation_id += 1  # Invalidate any already queued signals
        
        current_order = [c._page_index for c in self._cards]

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

        self._scene.reorder_annotations(new_order)
        self._doc_manager.reorder_pages(new_order)
        self._scene.rebuild_after_reorder(self._doc_manager, order=new_order)
        self.refresh_order(new_order)

    def refresh_order(self, new_order: list[int]) -> None:
        """Reorder cards to match new_order and update page numbers.

        new_order[new_pos] = old_page_index.
        """
        # Preserve scroll position
        vbar = self.verticalScrollBar()
        saved_scroll = vbar.value()

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

        # Reset all active states and re-apply to the correct card
        for card in self._cards:
            card.set_active(False)
        if 0 <= self._active_index < len(self._cards):
            self._cards[self._active_index].set_active(True)

        self._loaded_pages.clear()
        self._queued_pages.clear()

        # Restore scroll position (prevent jump to top)
        QTimer.singleShot(0, lambda: vbar.setValue(saved_scroll))
        QTimer.singleShot(50, self._load_visible_thumbnails)

    def rebuild_all(self, doc_manager: DocumentManager | None = None) -> None:
        """Clear and recreate all thumbnail cards from scratch."""
        dm = doc_manager or self._doc_manager
        if dm is None or self._scene is None:
            return

        self._loaded_pages.clear()
        self._queued_pages.clear()
        old_active = self._active_index
        self._active_index = -1

        self._thumb_generation_id += 1

        for card in self._cards:
            self._layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        page_count = dm.get_page_count()
        for i in range(page_count):
            card = ThumbnailCard(i)
            card.clicked.connect(self._on_card_clicked)
            self._layout.addWidget(card)
            self._cards.append(card)

        # Restore active page
        new_active = min(old_active, page_count - 1)
        if new_active >= 0:
            self.set_active_page(new_active)

        QTimer.singleShot(50, self._load_visible_thumbnails)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Show page context menu on right-click."""
        if not self._cards or self._viewer is None:
            return

        # Find which card was clicked
        pos_in_container = self._container.mapFrom(
            self.viewport(),
            self.viewport().mapFrom(self, event.pos()),
        )
        clicked_idx = -1
        for i, card in enumerate(self._cards):
            if card.geometry().contains(pos_in_container):
                clicked_idx = i
                break
        if clicked_idx < 0:
            return

        menu = QMenu(self)
        menu.setObjectName("pageContextMenu")

        act_add_above = QAction("Leere Seite davor einfügen", self)
        act_add_below = QAction("Leere Seite danach einfügen", self)
        act_duplicate = QAction("Seite duplizieren", self)
        act_delete = QAction("Seite löschen", self)
        act_delete.setEnabled(len(self._cards) > 1)

        menu.addAction(act_add_above)
        menu.addAction(act_add_below)
        menu.addSeparator()
        menu.addAction(act_duplicate)
        menu.addSeparator()
        menu.addAction(act_delete)

        viewer = self._viewer
        idx = clicked_idx
        act_add_above.triggered.connect(
            lambda: viewer.add_page(idx, "before"))
        act_add_below.triggered.connect(
            lambda: viewer.add_page(idx, "after"))
        act_duplicate.triggered.connect(
            lambda: viewer.duplicate_page(idx))
        act_delete.triggered.connect(
            lambda: viewer.delete_page(idx))

        menu.exec(event.globalPos())

    def set_active_page(self, page_index: int) -> None:
        """Highlight the given page in the sidebar.

        Args:
            page_index: Zero-based page index.
        """
        # Clear old active
        if 0 <= self._active_index < len(self._cards):
            self._cards[self._active_index].set_active(False)
        # Set new active
        if 0 <= page_index < len(self._cards):
            self._cards[page_index].set_active(True)
            self.ensureWidgetVisible(self._cards[page_index], 50, 50)
        self._active_index = page_index

    def _on_card_clicked(self, page_index: int) -> None:
        self.page_clicked.emit(page_index)

    def _on_scene_changed(self, rects: list) -> None:
        """Invalidate thumbnails that overlap with the changed area."""
        if getattr(self._scene, '_is_rendering_thumbnail', False):
            return
        if self._scene is None or not self._cards:
            return

        for rect in rects:
            for i, page_rect in enumerate(self._scene._page_rects):
                if rect.intersects(page_rect):
                    self.invalidate_thumb(i)

    def invalidate_thumb(self, page_idx: int) -> None:
        """Mark a thumbnail as needing re-render. Re-renders if visible."""
        self._loaded_pages.discard(page_idx)
        self._queued_pages.discard(page_idx)
        self._lazy_timer.start()

    def _load_visible_thumbnails(self) -> None:
        """Load thumbnails for visible cards + 2 buffer pages.

        Uses doc_manager.get_page_pixmap(dpi=36, use_hidpi=False) directly instead of
        scene.render() to avoid capturing gray placeholders from virtual
        rendering.
        """
        if self._doc_manager is None or not self._cards:
            return

        if self._thumb_worker is not None:
            worker_ref = self._thumb_worker
            self._thumb_worker = None
            try:
                worker_ref.cancel()
                for idx in worker_ref._indices:
                    self._queued_pages.discard(idx)
                # Keep python reference alive until C++ thread exits natively
                self._zombie_workers.add(worker_ref)
                worker_ref.finished.connect(lambda w=worker_ref: self._zombie_workers.discard(w))
            except RuntimeError:
                pass

        viewport_rect = self.viewport().rect()
        buffer = 2

        first_visible = -1
        last_visible = -1

        vp_global = self.viewport().mapToGlobal(QPoint(0, 0))

        for i, card in enumerate(self._cards):
            card_global = card.mapToGlobal(QPoint(0, 0))
            rel = card_global - vp_global
            card_rect = card.rect().translated(rel.x(), rel.y())
            if viewport_rect.intersects(card_rect):
                if first_visible == -1:
                    first_visible = i
                last_visible = i

        if first_visible == -1:
            first_visible = 0
            last_visible = min(4, len(self._cards) - 1)

        start = max(0, first_visible - buffer)
        end = min(len(self._cards) - 1, last_visible + buffer)

        indices = [i for i in range(start, end + 1) 
                   if i not in self._loaded_pages and i not in self._queued_pages]
        if not indices:
            return

        for i in indices:
            self._queued_pages.add(i)

        self._thumb_generation_id += 1
        self._thumb_worker = ThumbnailWorker(
            self._doc_manager, indices, self.THUMBNAIL_DPI, False, self._thumb_generation_id
        )
        self._thumb_worker.finished.connect(self._thumb_worker.deleteLater)
        self._thumb_worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._thumb_worker.start()

    def _on_thumbnail_ready(self, gen_id: int, idx: int, img: QImage) -> None:
        self._queued_pages.discard(idx)
        
        if gen_id != self._thumb_generation_id:
            return
            
        if idx < len(self._cards) and not img.isNull():
            self._loaded_pages.add(idx)
            pixmap = QPixmap.fromImage(img)
            
            # --- Overlay Annotations ---
            if self._scene is not None and idx < len(self._scene._page_items):
                overlay = QPixmap(pixmap.size())
                overlay.setDevicePixelRatio(pixmap.devicePixelRatio())
                overlay.fill(Qt.GlobalColor.transparent)
                
                self._scene._is_rendering_thumbnail = True
                page_item = self._scene._page_items[idx]
                
                try:
                    # We replace the pixmap instead of setVisible(False) because visibility 
                    # might not flush instantly or flawlessly in NoIndex QGraphicsScenes.
                    # A null QPixmap guarantees the placeholder/page is totally invisible.
                    old_pixmap = page_item.pixmap()
                    page_item.setPixmap(QPixmap())
                except RuntimeError:
                    # C++ object deleted by rapid scene.clear() calls in main thread
                    return
                
                ephemeral_items = self._scene.get_ephemeral_items()
                ephemeral_states = [(item, item.isVisible()) for item in ephemeral_items]
                for item, _ in ephemeral_states:
                    try:
                        item.setVisible(False)
                    except RuntimeError:
                        pass
                    
                overlay_was_visible = False
                if getattr(self._scene, '_selection_overlay', None):
                    try:
                        overlay_was_visible = self._scene._selection_overlay.isVisible()
                        self._scene._selection_overlay.setVisible(False)
                    except RuntimeError:
                        pass
                
                painter = QPainter(overlay)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                source_rect = self._scene.get_page_rect(idx)
                
                # Correct logical target rect scaling based on DPR
                dpr = overlay.devicePixelRatio()
                target_rect = QRectF(0, 0, overlay.width() / dpr, overlay.height() / dpr)
                
                self._scene.render(painter, target_rect, source_rect)
                painter.end()
                
                try:
                    page_item.setPixmap(old_pixmap)
                except RuntimeError:
                    pass
                self._scene._is_rendering_thumbnail = False
                
                for item, vis in ephemeral_states:
                    try:
                        item.setVisible(vis)
                    except RuntimeError:
                        pass
                    
                if getattr(self._scene, '_selection_overlay', None):
                    try:
                        self._scene._selection_overlay.setVisible(overlay_was_visible)
                    except RuntimeError:
                        pass
                
                p2 = QPainter(pixmap)
                p2.setRenderHint(QPainter.RenderHint.Antialiasing)
                p2.drawPixmap(0, 0, overlay)
                p2.end()
            # ---------------------------
            
            self._cards[idx].set_thumbnail(pixmap)
