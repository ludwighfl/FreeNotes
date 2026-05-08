"""Scrollable sidebar with lazy-loaded page thumbnails.

Extensively refactored into mixins to maintain architecture size limits.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QScrollArea,
    QWidget,
    QVBoxLayout,
)

from core.document_manager import DocumentManager
from core.thumbnail_worker import ThumbnailWorker
from ui.components.thumbnail_card import ThumbnailCard
from app.app_state import AppState

from ui.bars.sidebar_context_menu import SidebarContextMenuMixin
from ui.bars.sidebar_render import SidebarRenderMixin

# TYPE_CHECKING import to avoid circular dependency problems on init
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene
    from ui.windows.viewer_window import ViewerWindow


class SidebarWidget(SidebarContextMenuMixin, SidebarRenderMixin, QScrollArea):
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
        self._last_scene_changed_time: float = 0.0
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
            card = ThumbnailCard(i, doc_manager)
            card.clicked.connect(self._on_card_clicked)
            self._layout.addWidget(card)
            self._cards.append(card)

        if page_count > 0:
            self.set_active_page(0)

        QTimer.singleShot(250, self._load_visible_thumbnails)

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
        self._thumb_generation_id += 1

        # Restore scroll position (prevent jump to top)
        QTimer.singleShot(0, lambda: vbar.setValue(saved_scroll))
        QTimer.singleShot(250, self._load_visible_thumbnails)

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
            card = ThumbnailCard(i, dm)
            card.clicked.connect(self._on_card_clicked)
            self._layout.addWidget(card)
            self._cards.append(card)

        # Restore active page
        new_active = min(old_active, page_count - 1)
        if new_active >= 0:
            self.set_active_page(new_active)

        QTimer.singleShot(250, self._load_visible_thumbnails)

    # ------------------------------------------------------------------
    # Incremental card insert / remove
    # ------------------------------------------------------------------

    def insert_card(self, at_index: int) -> None:
        """Insert a single thumbnail card at *at_index* and renumber subsequent cards.

        Much cheaper than rebuild_all: existing cards and their loaded
        thumbnails are preserved — only page numbers are updated.
        """
        self._thumb_generation_id += 1
        card = ThumbnailCard(at_index, self._doc_manager)
        card.clicked.connect(self._on_card_clicked)
        self._cards.insert(at_index, card)
        self._layout.insertWidget(at_index, card)

        # Renumber cards after the insertion point
        for i in range(at_index + 1, len(self._cards)):
            self._cards[i].update_page_number(i)

        # Shift loaded/queued page tracking
        self._loaded_pages.clear()
        self._queued_pages.clear()

        QTimer.singleShot(250, self._load_visible_thumbnails)

    def remove_card(self, page_idx: int) -> None:
        """Remove the card at *page_idx* and renumber subsequent cards.

        Much cheaper than rebuild_all: existing cards and their loaded
        thumbnails are preserved — only page numbers are updated.
        """
        if page_idx < 0 or page_idx >= len(self._cards):
            return

        self._thumb_generation_id += 1
        card = self._cards.pop(page_idx)
        self._layout.removeWidget(card)
        card.deleteLater()

        # Renumber cards after the removal point
        for i in range(page_idx, len(self._cards)):
            self._cards[i].update_page_number(i)

        # Shift loaded/queued page tracking
        self._loaded_pages.clear()
        self._queued_pages.clear()

        # Fix active index
        if self._active_index == page_idx:
            self._active_index = -1
        elif self._active_index > page_idx:
            self._active_index -= 1

        QTimer.singleShot(250, self._load_visible_thumbnails)

    def set_active_page(self, page_index: int) -> None:
        """Highlight the given page in the sidebar and ensure it is fully visible.

        Args:
            page_index: Zero-based page index.
        """
        # Clear old active
        if 0 <= self._active_index < len(self._cards):
            self._cards[self._active_index].set_active(False)
        # Set new active
        if 0 <= page_index < len(self._cards):
            card = self._cards[page_index]
            card.set_active(True)
            # Ensure the active thumbnail is fully visible in the sidebar.
            # Defer execution to allow the layout engine to calculate geometry of newly added cards.
            def _scroll():
                try:
                    self.ensureWidgetVisible(card, 0, 10)
                except RuntimeError:
                    pass  # Card was deleted by a rapid rebuild
            QTimer.singleShot(0, _scroll)
        self._active_index = page_index



    def _on_card_clicked(self, page_index: int) -> None:
        self.page_clicked.emit(page_index)
