"""Graphics scene for PDF pages – arranges all pages vertically and dispatches tool events."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QPointF, Signal, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsSceneMouseEvent,
)

from core.document_manager import DocumentManager
from core import undo_stack
from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem
from items.text_box_item import TextBoxItem
from items.selection_overlay_item import SelectionOverlayItem
from items.bounding_box_handle_manager import BoundingBoxHandleManager
from items.shape_item import ShapeItem
from ui.scene_registry import SceneRegistryMixin
from ui.scene_clipboard import SceneClipboardMixin

# TYPE_CHECKING import to avoid circular dependency
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.base_tool import BaseTool


class PageScene(SceneRegistryMixin, SceneClipboardMixin, QGraphicsScene):
    """QGraphicsScene that holds all PDF pages stacked vertically.

    Each page is a QGraphicsPixmapItem placed below the previous one
    with a 20px gap between pages. Supports HiDPI pixmaps via
    devicePixelRatio – layout uses logical sizes.

    Also dispatches mouse events to the active tool for drawing.

    Functionality is split across mixins:
        SceneRegistryMixin  – per-page item tracking (strokes, highlights, textboxes)
        SceneClipboardMixin – delete/copy/cut/paste + serialization
    """

    PAGE_GAP: int = 20

    tool_switch_requested = Signal(str)
    selection_changed = Signal()

    def __init__(self, parent: object = None) -> None:
        super().__init__(parent)
        self._page_items: list[QGraphicsPixmapItem] = []
        self._page_rects: list[QRectF] = []
        self._active_tool: BaseTool | None = None
        self._stroke_items: dict[int, list[StrokeItem]] = {}
        self._highlight_items: dict[int, list[HighlightItem]] = {}
        self._text_box_items: dict[int, list[TextBoxItem]] = {}
        self._shape_items: dict[int, list] = {}

        # Disable BSP tree for dynamic item compatibility (fixes zoom ghosts)
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)

        # Central selection state
        self._selected_items: set = set()
        self._selection_overlay: SelectionOverlayItem = SelectionOverlayItem()
        self.addItem(self._selection_overlay)
        self._selection_overlay.setVisible(False)

        # Bounding box resize handles
        self._bbox_handle_manager = BoundingBoxHandleManager(self)
        self.selection_changed.connect(self._on_selection_changed)

    def load_document(self, doc_manager: DocumentManager) -> None:
        """Load all pages from the document manager into the scene.

        Args:
            doc_manager: An open DocumentManager instance.
        """
        self.clear()
        self._page_items.clear()
        self._page_rects.clear()
        self._stroke_items.clear()
        self._highlight_items.clear()
        self._text_box_items.clear()
        self._selected_items.clear()

        # Recreate overlay (self.clear() destroys all scene items)
        self._selection_overlay = SelectionOverlayItem()
        self.addItem(self._selection_overlay)
        self._selection_overlay.setVisible(False)

        page_count = doc_manager.get_page_count()
        if page_count == 0:
            return

        y_offset: float = self.PAGE_GAP

        for i in range(page_count):
            pixmap = doc_manager.get_page_pixmap(i)
            item = QGraphicsPixmapItem(pixmap)
            item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

            # Use logical size for layout (accounts for devicePixelRatio)
            dpr = pixmap.devicePixelRatio()
            logical_w = pixmap.width() / dpr
            logical_h = pixmap.height() / dpr

            item.setPos(0, y_offset)
            self._page_items.append(item)
            self.addItem(item)

            page_rect = QRectF(0, y_offset, logical_w, logical_h)
            self._page_rects.append(page_rect)

            y_offset += logical_h + self.PAGE_GAP

        # Center all pages horizontally
        if self._page_items:
            max_width = max(
                item.pixmap().width() / item.pixmap().devicePixelRatio()
                for item in self._page_items
            )
            for i, item in enumerate(self._page_items):
                pix = item.pixmap()
                logical_w = pix.width() / pix.devicePixelRatio()
                logical_h = pix.height() / pix.devicePixelRatio()
                x_offset = (max_width - logical_w) / 2.0
                item.setPos(x_offset, item.pos().y())
                self._page_rects[i] = QRectF(
                    x_offset, item.pos().y(), logical_w, logical_h
                )

    # ------------------------------------------------------------------
    # Tool management
    # ------------------------------------------------------------------

    def set_tool(self, tool: BaseTool) -> None:
        """Set the active tool, deactivating any previous tool.

        Args:
            tool: The new tool to activate.
        """
        if self._active_tool is not None:
            self._active_tool.deactivate(self)
        self._active_tool = tool
        if self._active_tool is not None:
            self._active_tool.activate(self)

    @property
    def active_tool(self) -> BaseTool | None:
        """Return the currently active tool."""
        return self._active_tool

    # ------------------------------------------------------------------
    # Mouse event dispatch to active tool
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Dispatch press to active tool, then call super."""
        # Deselect all textboxes when clicking empty space with non-text tool
        from tools.text_tool import TextTool

        if not isinstance(self._active_tool, TextTool):
            # Check if click is NOT on a TextBoxItem
            items_at = self.items(
                QRectF(
                    event.scenePos().x() - 2,
                    event.scenePos().y() - 2,
                    4,
                    4,
                )
            )
            has_textbox = any(isinstance(i, TextBoxItem) for i in items_at)
            if not has_textbox:
                self.deselect_all_textboxes()

        if self._active_tool is not None:
            self._active_tool.on_press(event, self)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Dispatch move to active tool, then call super."""
        if self._active_tool is not None:
            self._active_tool.on_move(event, self)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Dispatch release to active tool, then call super."""
        if self._active_tool is not None:
            self._active_tool.on_release(event, self)
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Key events
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key events: forward to editing TextBox, Escape, Delete, Copy, Paste."""
        # Forward to editing TextBox if one has focus
        focus = self.focusItem()
        if isinstance(focus, TextBoxItem) and focus._is_editing:
            focus.keyPressEvent(event)
            event.accept()
            return

        from PySide6.QtGui import QKeySequence
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selected()
            event.accept()
            return
        elif event.matches(QKeySequence.StandardKey.Cut):
            self.cut_selected()
            event.accept()
            return
        elif event.matches(QKeySequence.StandardKey.Paste):
            self.paste_clipboard()
            event.accept()
            return

        key = event.key()

        # Escape: deselect all textboxes and selections
        if key == Qt.Key.Key_Escape:
            self.deselect_all_textboxes()
            self.clear_selection()
            event.accept()
            return

        # Delete/Backspace: delete selected items globally
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
            event.accept()
            return

        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Page queries
    # ------------------------------------------------------------------

    def get_page_rect(self, page_index: int) -> QRectF:
        """Return the bounding rectangle of a specific page in scene coords.

        Args:
            page_index: Zero-based page index.

        Returns:
            QRectF of the page, or an empty QRectF if index is out of range.
        """
        if 0 <= page_index < len(self._page_rects):
            return self._page_rects[page_index]
        return QRectF()

    def get_page_index_at(self, scene_pos: QPointF) -> int:
        """Determine which page contains the given scene position.

        Args:
            scene_pos: A position in scene coordinates.

        Returns:
            Zero-based page index, or -1 if outside all pages.
        """
        for i, rect in enumerate(self._page_rects):
            if rect.contains(scene_pos):
                return i
        return -1

    @property
    def page_count(self) -> int:
        """Number of pages currently in the scene."""
        return len(self._page_items)

    # ------------------------------------------------------------------
    # Page reorder
    # ------------------------------------------------------------------

    def reorder_annotations(self, new_order: list[int]) -> None:
        """Remap annotation dicts according to new_order.

        new_order[new_pos] = old_page_index.
        Must be called BEFORE doc_manager.reorder_pages().
        """

        def remap(d: dict) -> dict:
            new_d: dict = {}
            for new_pos, old_idx in enumerate(new_order):
                if old_idx in d:
                    items = d[old_idx]
                    new_d[new_pos] = items
                    for item in items:
                        if hasattr(item, '_page_index'):
                            item._page_index = new_pos
            return new_d

        self._stroke_items = remap(self._stroke_items)
        self._highlight_items = remap(self._highlight_items)
        self._text_box_items = remap(self._text_box_items)
        self._shape_items = remap(self._shape_items)

    def rebuild_after_reorder(self, doc_manager: DocumentManager) -> None:
        """Rebuild page pixmaps and reposition annotations after reorder.

        Must be called AFTER doc_manager.reorder_pages().
        """
        page_count = doc_manager.get_page_count()
        if page_count == 0:
            return

        # Collect all annotation items and temporarily remove from scene
        all_annotations: dict[int, list] = {}
        for idx in range(page_count):
            items = []
            for d in (self._stroke_items, self._highlight_items,
                      self._text_box_items, self._shape_items):
                items.extend(d.get(idx, []))
            all_annotations[idx] = items

        # Store old page rects for offset calculation
        old_page_rects = list(self._page_rects)

        # Remove old page pixmap items
        for pix_item in self._page_items:
            self.removeItem(pix_item)
        self._page_items.clear()
        self._page_rects.clear()

        # Re-render pages in new order
        y_offset: float = self.PAGE_GAP
        for i in range(page_count):
            pixmap = doc_manager.get_page_pixmap(i)
            item = QGraphicsPixmapItem(pixmap)
            item.setTransformationMode(
                Qt.TransformationMode.SmoothTransformation)

            dpr = pixmap.devicePixelRatio()
            logical_w = pixmap.width() / dpr
            logical_h = pixmap.height() / dpr

            item.setPos(0, y_offset)
            self._page_items.append(item)
            self.addItem(item)

            page_rect = QRectF(0, y_offset, logical_w, logical_h)
            self._page_rects.append(page_rect)
            y_offset += logical_h + self.PAGE_GAP

        # Center horizontally
        if self._page_items:
            max_width = max(
                it.pixmap().width() / it.pixmap().devicePixelRatio()
                for it in self._page_items
            )
            for i, it in enumerate(self._page_items):
                pix = it.pixmap()
                lw = pix.width() / pix.devicePixelRatio()
                lh = pix.height() / pix.devicePixelRatio()
                x_off = (max_width - lw) / 2.0
                it.setPos(x_off, it.pos().y())
                self._page_rects[i] = QRectF(
                    x_off, it.pos().y(), lw, lh)

        # Reposition annotation items to new page y-offsets
        for idx in range(page_count):
            if idx >= len(self._page_rects):
                break
            new_rect = self._page_rects[idx]
            # Get old rect for this page's annotations (use old_page_rects if available)
            for item in all_annotations.get(idx, []):
                old_pos = item.pos()
                # Find which old page this item was on based on its old _page_index
                old_page_idx = idx  # annotations already remapped
                if old_page_idx < len(old_page_rects):
                    old_rect = old_page_rects[old_page_idx]
                    # Compute relative position within old page
                    rel_x = old_pos.x() - old_rect.x()
                    rel_y = old_pos.y() - old_rect.y()
                    # Apply to new page position
                    item.setPos(QPointF(
                        new_rect.x() + rel_x,
                        new_rect.y() + rel_y,
                    ))

    # ------------------------------------------------------------------
    # Page insert / remove
    # ------------------------------------------------------------------

    def insert_page(self, at_index: int, doc_manager: DocumentManager) -> None:
        """Insert an empty annotation slot at at_index.

        Shifts all annotation indices >= at_index up by 1.
        """
        for d in (self._stroke_items, self._highlight_items,
                  self._text_box_items, self._shape_items):
            new_d: dict = {}
            for idx, items in d.items():
                new_idx = idx + 1 if idx >= at_index else idx
                for item in items:
                    if hasattr(item, '_page_index') and item._page_index >= at_index:
                        item._page_index += 1
                new_d[new_idx] = items
            d.clear()
            d.update(new_d)

    def remove_page(self, page_idx: int, doc_manager: DocumentManager) -> None:
        """Remove all annotations on page_idx and shift indices down."""
        for d in (self._stroke_items, self._highlight_items,
                  self._text_box_items, self._shape_items):
            # Remove items on the deleted page from scene
            for item in d.get(page_idx, []):
                self.removeItem(item)
            # Re-index
            new_d: dict = {}
            for idx, items in d.items():
                if idx == page_idx:
                    continue
                new_idx = idx - 1 if idx > page_idx else idx
                for item in items:
                    if hasattr(item, '_page_index') and item._page_index > page_idx:
                        item._page_index -= 1
                new_d[new_idx] = items
            d.clear()
            d.update(new_d)

    def clone_page_annotations(
        self, source_idx: int, target_idx: int
    ) -> None:
        """Deep-copy annotations from source_idx to target_idx."""
        mapping = [
            (self._stroke_items, StrokeItem),
            (self._highlight_items, HighlightItem),
            (self._text_box_items, TextBoxItem),
            (self._shape_items, ShapeItem),
        ]
        for d, item_cls in mapping:
            for item in d.get(source_idx, []):
                try:
                    data = item.to_dict()
                    new_item = item_cls.from_dict(data)
                    new_item._page_index = target_idx
                    d.setdefault(target_idx, []).append(new_item)
                    self.addItem(new_item)
                except Exception:
                    pass  # skip items that can't be cloned

    def save_page_annotations(self, page_idx: int) -> dict:
        """Save annotation item references for undo (removes from scene)."""
        saved: dict = {
            "strokes": list(self._stroke_items.get(page_idx, [])),
            "highlights": list(self._highlight_items.get(page_idx, [])),
            "textboxes": list(self._text_box_items.get(page_idx, [])),
            "shapes": list(self._shape_items.get(page_idx, [])),
        }
        return saved

    def restore_page_annotations(
        self, page_idx: int, saved: dict
    ) -> None:
        """Restore previously saved annotation items to page_idx."""
        mapping = {
            "strokes": self._stroke_items,
            "highlights": self._highlight_items,
            "textboxes": self._text_box_items,
            "shapes": self._shape_items,
        }
        for key, items in saved.items():
            d = mapping[key]
            d.setdefault(page_idx, [])
            for item in items:
                item._page_index = page_idx
                if item.scene() is None:
                    self.addItem(item)
                d[page_idx].append(item)

    # ------------------------------------------------------------------
    # Eraser cursor visibility
    # ------------------------------------------------------------------

    def set_eraser_cursor_visible(self, visible: bool) -> None:
        """Show/hide the eraser cursor item if the active tool is an eraser."""
        from tools.eraser_tool import EraserTool
        if isinstance(self._active_tool, EraserTool):
            if self._active_tool._cursor_item is not None:
                self._active_tool._cursor_item.setVisible(visible)

    def get_ephemeral_items(self) -> list:
        """Return a list of UI graphics items that shouldn't be rendered in exporting or thumbnails."""
        items = []
        
        # Active tool cursor (e.g. eraser circle)
        from tools.eraser_tool import EraserTool
        if isinstance(self._active_tool, EraserTool):
            if self._active_tool._cursor_item is not None:
                try:
                    if self._active_tool._cursor_item.isVisible():
                        items.append(self._active_tool._cursor_item)
                except RuntimeError:
                    pass
                
        # TextBox selection frames are handled in their respective paint methods dynamically.
        
        return items

    # ------------------------------------------------------------------
    # Central selection management
    # ------------------------------------------------------------------

    def set_selection(self, items: list) -> None:
        """Replace the entire selection with *items*."""
        old = set(self._selected_items)
        self._selected_items.clear()
        for item in old:
            self._deselect_item(item)
        for item in items:
            self._select_item(item)
            self._selected_items.add(item)
        self._update_selection_overlay()
        self.selection_changed.emit()

    def add_to_selection(self, item) -> None:
        """Add a single item to the selection."""
        if item not in self._selected_items:
            self._select_item(item)
            self._selected_items.add(item)
            self._update_selection_overlay()
            self.selection_changed.emit()

    def remove_from_selection(self, item) -> None:
        """Remove a single item from the selection."""
        if item in self._selected_items:
            self._deselect_item(item)
            self._selected_items.discard(item)
            self._update_selection_overlay()
            self.selection_changed.emit()

    def clear_selection(self) -> None:
        """Deselect everything."""
        for item in set(self._selected_items):
            self._deselect_item(item)
        self._selected_items.clear()
        self._ensure_overlay().setVisible(False)
        self.selection_changed.emit()

    def get_selected_items(self) -> list:
        """Return a snapshot of the current selection."""
        return list(self._selected_items)

    def _select_item(self, item) -> None:
        """Mark *item* as selected (visual feedback) if it is the ONLY selected item.
        If there are multiple selected items, individual markers are hidden."""
        if len(self._selected_items) >= 2:
            return  # Will be hidden by _on_selection_changed
            
        if isinstance(item, TextBoxItem):
            item.set_selected_custom(True)
        elif isinstance(item, ShapeItem):
            item.set_selected_custom(True)
        elif isinstance(item, (StrokeItem, HighlightItem)):
            item.set_selected(True)

    def _deselect_item(self, item) -> None:
        """Remove selection visual from *item*."""
        if isinstance(item, TextBoxItem):
            item.set_selected_custom(False)
        elif isinstance(item, ShapeItem):
            item.set_selected_custom(False)
        elif isinstance(item, (StrokeItem, HighlightItem)):
            item.set_selected(False)

    def _ensure_overlay(self) -> SelectionOverlayItem:
        """Return the selection overlay, recreating it if the C++ side was deleted."""
        try:
            self._selection_overlay.isVisible()  # probe C++ object
        except RuntimeError:
            self._selection_overlay = SelectionOverlayItem()
            self.addItem(self._selection_overlay)
            self._selection_overlay.setVisible(False)
        return self._selection_overlay

    def _update_selection_overlay(self) -> None:
        """Refresh the multi-selection overlay bounding box."""
        self._ensure_overlay().update_from_items(
            self._selected_items, self)
        self._bbox_handle_manager.reposition()

    def _on_selection_changed(self) -> None:
        """React to selection changes: update individual visuals and bounding box resize handles."""
        items = list(self._selected_items)
        count = len(items)

        # 1. Update individual item visuals based on selection count
        if count >= 2:
            # Hide individual borders/handles, the Overlay will show the combined box
            for item in items:
                if isinstance(item, TextBoxItem):
                    item.set_selected_custom(False)
                elif isinstance(item, ShapeItem):
                    item.set_selected_custom(False)
                elif isinstance(item, (StrokeItem, HighlightItem)):
                    item.set_selected(False)
        elif count == 1:
            # Show individual border/handles for the single selected item
            item = items[0]
            if isinstance(item, TextBoxItem):
                item.set_selected_custom(True)
            elif isinstance(item, ShapeItem):
                item.set_selected_custom(True)
            elif isinstance(item, (StrokeItem, HighlightItem)):
                item.set_selected(True)

        # 2. Attach or detach the common bounding box resize handles
        if count == 0:
            self._bbox_handle_manager.detach()
        elif count == 1:
            # ShapeItem has its own handle system
            if isinstance(items[0], (StrokeItem, HighlightItem)):
                self._bbox_handle_manager.attach_to(items[0])
            else:
                self._bbox_handle_manager.detach()
        elif count >= 2:
            # Only allow resizing of multiple items if NO TextBoxItem is selected
            has_textbox = any(isinstance(i, TextBoxItem) for i in items)
            if not has_textbox:
                overlay = self._ensure_overlay()
                self._bbox_handle_manager.attach_to(overlay)
            else:
                self._bbox_handle_manager.detach()
