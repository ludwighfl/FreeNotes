"""Nebo/Goodnotes-style drag-reorder for sidebar thumbnails.

The card stays hidden in the layout. A pixmap snapshot floats above
the viewport as the drag handle. A gap indicator shows the drop target.
Cards shift when 70% overlap is reached. No widget reparenting.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QEvent, Qt, QPoint, QTimer
from PySide6.QtGui import QMouseEvent, QColor
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QGraphicsDropShadowEffect,
)
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ui.bars.sidebar_widget import ThumbnailCard, SidebarWidget


class _GapIndicator(QFrame):
    """Visual placeholder marking the drop target."""

    def __init__(self, height: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setStyleSheet(
            "background: rgba(59, 123, 245, 0.12);"
            "border: 2px dashed rgba(59, 123, 245, 0.5);"
            "border-radius: 4px;"
        )


class DragReorderController(QObject):

    HOLD_DELAY_MS: int = 0
    OVERLAP_RATIO: float = 0.70
    SCROLL_MARGIN: int = 40
    SCROLL_SPEED: int = 15

    def __init__(
        self,
        sidebar: SidebarWidget,
        get_cards: Callable[[], list],
        get_spacing: Callable[[], int],
        on_reorder: Callable[[list[int]], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._sidebar = sidebar
        self._get_cards = get_cards
        self._get_spacing = get_spacing
        self._on_reorder = on_reorder

        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._on_hold_ready)

        self._can_drag = False
        self._dragging = False
        self._busy = False
        self._drag_card = None
        self._ghost: QLabel | None = None  # pixmap copy, no reparenting
        self._gap: _GapIndicator | None = None
        self._cursor_offset_y = 0
        self._ghost_x = 0
        self._source_idx = -1
        self._saved_order: list[int] = []
        self._press_pos = None

        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(16)
        self._scroll_timer.timeout.connect(self._on_auto_scroll)
        self._scroll_dir = 0

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    # ── Public API ───────────────────────────────────────

    def on_press(self, card, event: QMouseEvent) -> None:
        if self._dragging or self._busy:
            return
        self._press_pos = event.pos()
        self._drag_card = card
        self._can_drag = False
        self._hold_timer.start(self.HOLD_DELAY_MS)

    def on_move(self, card, event: QMouseEvent) -> None:
        if self._busy or card is not self._drag_card or not self._can_drag:
            return
        if not self._dragging:
            from PySide6.QtWidgets import QApplication
            diff = event.pos() - self._press_pos
            if diff.manhattanLength() < QApplication.startDragDistance():
                return
            self._begin_drag(card, event)
        if self._dragging:
            self._continue_drag(event)

    def on_release(self, card, event: QMouseEvent) -> None:
        self._hold_timer.stop()
        if self._dragging and not self._busy:
            self._end_drag()
        self._can_drag = False
        if not self._dragging:
            self._drag_card = None

    def _on_hold_ready(self) -> None:
        self._can_drag = True

    # ── Drag start ───────────────────────────────────────

    def _begin_drag(self, card, event: QMouseEvent) -> None:
        self._dragging = True
        cards = self._get_cards()
        if card not in cards:
            self._dragging = False
            return
        self._source_idx = cards.index(card)
        self._saved_order = [c._page_index for c in cards]

        layout = self._sidebar._layout
        vp = self._sidebar.viewport()

        # Cursor offset from card top
        card_global_y = card.mapToGlobal(QPoint(0, 0)).y()
        self._cursor_offset_y = event.globalPos().y() - card_global_y

        # Create floating ghost (pixmap snapshot on viewport)
        pixmap = card.grab()
        self._ghost = QLabel(vp)
        self._ghost.setPixmap(pixmap)
        self._ghost.setFixedSize(pixmap.size())
        self._ghost.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        shadow = QGraphicsDropShadowEffect(self._ghost)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 100))
        self._ghost.setGraphicsEffect(shadow)

        # Position ghost at card location
        card_pos_in_vp = self._sidebar._container.mapTo(vp, card.pos())
        self._ghost.move(card_pos_in_vp)
        self._ghost_x = card_pos_in_vp.x()
        self._ghost.show()
        self._ghost.raise_()

        # Prevent scrollbar jump by preserving its value during layout swap
        vbar = self._sidebar.verticalScrollBar()
        saved_scroll = vbar.value()

        # Hide card and insert gap at its position
        layout.removeWidget(card)
        card.setVisible(False)
        self._gap = _GapIndicator(card.height(), self._sidebar._container)
        layout.insertWidget(self._source_idx, self._gap)
        
        layout.activate()
        vbar.setValue(saved_scroll)

        # Capture mouse on viewport
        vp.setMouseTracking(True)
        vp.installEventFilter(self)

    # ── Drag move ────────────────────────────────────────

    def _continue_drag(self, event: QMouseEvent) -> None:
        self._position_ghost(event)
        self._update_gap()
        self._update_auto_scroll(event)

    def _update_auto_scroll(self, event: QMouseEvent) -> None:
        vp = self._sidebar.viewport()
        cursor_vp_y = vp.mapFromGlobal(event.globalPos()).y()

        if cursor_vp_y < self.SCROLL_MARGIN:
            self._scroll_dir = -1
            if not self._scroll_timer.isActive():
                self._scroll_timer.start()
        elif cursor_vp_y > vp.height() - self.SCROLL_MARGIN:
            self._scroll_dir = 1
            if not self._scroll_timer.isActive():
                self._scroll_timer.start()
        else:
            self._scroll_dir = 0
            self._scroll_timer.stop()

    def _on_auto_scroll(self) -> None:
        if not self._dragging or self._scroll_dir == 0:
            self._scroll_timer.stop()
            return

        vbar = self._sidebar.verticalScrollBar()
        old_val = vbar.value()
        vbar.setValue(old_val + self._scroll_dir * self.SCROLL_SPEED)

        if vbar.value() != old_val:
            self._update_gap()

    def _position_ghost(self, event: QMouseEvent) -> None:
        if not self._ghost:
            return
        vp = self._sidebar.viewport()
        cursor_vp = vp.mapFromGlobal(event.globalPos())
        x = self._ghost_x
        y = cursor_vp.y() - self._cursor_offset_y
        self._ghost.move(x, y)

    def _update_gap(self) -> None:
        """Shift gap using the 70%-overlap rule."""
        if not self._gap or not self._ghost:
            return

        vp = self._sidebar.viewport()
        container = self._sidebar._container
        layout = self._sidebar._layout

        ghost_top = self._ghost.y()
        ghost_bottom = ghost_top + self._ghost.height()

        gap_idx = layout.indexOf(self._gap)
        if gap_idx < 0:
            return

        # Shift gap DOWN
        while gap_idx < layout.count() - 1:
            item = layout.itemAt(gap_idx + 1)
            if not item or not item.widget():
                break
            w = item.widget()
            if not hasattr(w, '_page_index'):
                break
            w_top = container.mapTo(vp, w.pos()).y()
            w_h = w.height()
            if w_h <= 0:
                break
            overlap = max(0, min(ghost_bottom, w_top + w_h) - max(ghost_top, w_top))
            if overlap >= self.OVERLAP_RATIO * w_h:
                vbar = self._sidebar.verticalScrollBar()
                saved_scroll = vbar.value()

                layout.removeWidget(self._gap)
                layout.insertWidget(gap_idx + 1, self._gap)
                layout.activate()
                
                vbar.setValue(saved_scroll)
                gap_idx += 1
            else:
                break

        # Shift gap UP
        gap_idx = layout.indexOf(self._gap)
        if gap_idx < 0:
            return
        while gap_idx > 0:
            item = layout.itemAt(gap_idx - 1)
            if not item or not item.widget():
                break
            w = item.widget()
            if not hasattr(w, '_page_index'):
                break
            w_top = container.mapTo(vp, w.pos()).y()
            w_h = w.height()
            if w_h <= 0:
                break
            overlap = max(0, min(ghost_bottom, w_top + w_h) - max(ghost_top, w_top))
            if overlap >= self.OVERLAP_RATIO * w_h:
                vbar = self._sidebar.verticalScrollBar()
                saved_scroll = vbar.value()

                layout.removeWidget(self._gap)
                layout.insertWidget(gap_idx - 1, self._gap)
                layout.activate()
                
                vbar.setValue(saved_scroll)
                gap_idx -= 1
            else:
                break

    # ── Drag end ─────────────────────────────────────────

    def _end_drag(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            vp = self._sidebar.viewport()
            vp.setMouseTracking(False)
            vp.removeEventFilter(self)

            layout = self._sidebar._layout

            gap_pos = self._find_gap_card_index()

            # Remove ghost
            if self._ghost:
                self._ghost.setGraphicsEffect(None)
                self._ghost.hide()
                self._ghost.deleteLater()
                self._ghost = None

            # Remove gap
            if self._gap:
                layout.removeWidget(self._gap)
                self._gap.hide()
                self._gap.deleteLater()
                self._gap = None

            # Show card again
            if self._drag_card:
                layout.insertWidget(self._source_idx, self._drag_card)
                self._drag_card.setVisible(True)

            # Build new order
            new_order = list(self._saved_order)
            if gap_pos != self._source_idx:
                moved = new_order.pop(self._source_idx)
                new_order.insert(gap_pos, moved)

            if new_order != self._saved_order:
                self._on_reorder(new_order)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[DRAG-ERROR] Exception during drag end: {e}")
            # Show card if anything goes wrong
            if self._drag_card:
                try:
                    layout.insertWidget(self._source_idx, self._drag_card)
                    self._drag_card.setVisible(True)
                except Exception:
                    pass
        finally:
            self._reset_state()

    def _cancel_drag(self) -> None:
        if not self._dragging or self._busy:
            return
        self._busy = True
        try:
            vp = self._sidebar.viewport()
            vp.setMouseTracking(False)
            vp.removeEventFilter(self)

            if self._ghost:
                self._ghost.setGraphicsEffect(None)
                self._ghost.hide()
                self._ghost.deleteLater()
                self._ghost = None

            if self._gap:
                self._sidebar._layout.removeWidget(self._gap)
                self._gap.hide()
                self._gap.deleteLater()
                self._gap = None

            if self._drag_card:
                self._sidebar._layout.insertWidget(self._source_idx, self._drag_card)
                self._drag_card.setVisible(True)
        except Exception:
            pass
        finally:
            self._reset_state()

    def _reset_state(self) -> None:
        self._scroll_timer.stop()
        self._scroll_dir = 0
        self._dragging = False
        self._can_drag = False
        self._drag_card = None
        self._source_idx = -1
        self._saved_order = []
        self._ghost_x = 0
        self._busy = False

    def _find_gap_card_index(self) -> int:
        layout = self._sidebar._layout
        card_pos = 0
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if not item:
                continue
            w = item.widget()
            if w is self._gap:
                return card_pos
            if w and hasattr(w, '_page_index'):
                card_pos += 1
        return card_pos

    # ── Event filter ─────────────────────────────────────

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if not self._dragging or self._busy:
            return False
        if obj is self._sidebar.viewport():
            etype = event.type()
            if etype == QEvent.Type.MouseMove:
                self._continue_drag(event)
                return True
            if etype == QEvent.Type.MouseButtonRelease:
                self._end_drag()
                return True
            if etype == QEvent.Type.Leave:
                self._cancel_drag()
                return True
        return False
