"""Single thumbnail card for the sidebar."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QPixmap, QPainter, QFont, QColor, QBrush, QMouseEvent,
)
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
)


class PageBadge(QLabel):
    """Semi-transparent badge showing the page number."""
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.setObjectName("pageBadge")
        # Don't block click events on the thumbnail
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
    def set_page_number(self, index: int) -> None:
        self.setText(str(index + 1))
        self.adjustSize()


class ThumbnailCard(QFrame):
    """Single thumbnail card: page image + page number badge."""

    clicked = Signal(int)

    THUMB_WIDTH: int = 160
    ACTIVE_BORDER_COLOR: str = "#3B7BF5"

    def __init__(self, page_index: int, doc_manager=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page_index: int = page_index
        self._is_active: bool = False
        self._thumb_label: QLabel = QLabel(self)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self._badge = PageBadge(self)
        self._badge.set_page_number(self._page_index)
        self._badge.raise_()
        
        # Start shimmer effect for skeleton loading state
        from ui.animations.shimmer import ShimmerOverlay
        self._shimmer = ShimmerOverlay(self._thumb_label, border_radius=4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        layout.addWidget(self._thumb_label)

        self.setObjectName("thumbnailCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Store aspect ratio for responsive resizing
        self._aspect_ratio = 1.0 / 1.414
        if doc_manager is not None:
            w, h = doc_manager.get_page_size(page_index)
            if h > 0:
                self._aspect_ratio = w / h
                
        # Set initial height based on THUMB_WIDTH, but let layout stretch width
        inner_w = self.THUMB_WIDTH - 8
        height = int(inner_w / self._aspect_ratio) + 8
        self.setFixedHeight(height)
        self.setMinimumWidth(100)
        
        self._update_style()
        self._position_badge()

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        """Set the thumbnail pixmap, scaled to THUMB_WIDTH with page badge."""
        if getattr(self, '_shimmer', None):
            self._shimmer.stop()
            self._shimmer = None
            
        if pixmap.isNull():
            return
            
        self._original_pixmap = pixmap
        self._apply_pixmap()

        from ui.animations.thumbnail import ThumbnailFadeAnimation
        ThumbnailFadeAnimation(
            label=self._thumb_label,
            duration=200,
            parent=self,
        ).start()

    def _apply_pixmap(self) -> None:
        """Scale and render the pixmap based on the current actual width."""
        pixmap = getattr(self, '_original_pixmap', None)
        if pixmap is None or pixmap.isNull():
            return
            
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        screen_dpr = app.primaryScreen().devicePixelRatio() if app and app.primaryScreen() else 1.0
        
        inner_w = self.width() - 8
        inner_h = int(inner_w * (pixmap.height() / pixmap.width()))
        
        physical_w = int(inner_w * screen_dpr)
        physical_h = int(inner_h * screen_dpr)
        
        scaled = pixmap.scaled(
            physical_w, physical_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        scaled.setDevicePixelRatio(screen_dpr)
        
        self.setFixedHeight(inner_h + 8)
        self._thumb_label.setPixmap(scaled)



    def _find_sidebar(self):
        w = self.parent()
        while w is not None:
            from ui.bars.sidebar_widget import SidebarWidget
            if isinstance(w, SidebarWidget):
                return w
            w = w.parent()
        return None

    def update_page_number(self, new_index: int) -> None:
        """Update the page index and re-render the badge."""
        self._page_index = new_index
        self._badge.set_page_number(new_index)
        self._position_badge()

    def _position_badge(self) -> None:
        """Position the badge in the bottom right corner."""
        badge_w = self._badge.width()
        badge_h = self._badge.height()
        margin = 8  # 4px from layout + 4px inner padding
        self._badge.move(self.width() - badge_w - margin, self.height() - badge_h - margin)

    def set_active(self, active: bool) -> None:
        """Set whether this card is the active page."""
        if self._is_active != active:
            self._is_active = active
            self._update_style()

    def _update_style(self) -> None:
        self.setProperty("active", self._is_active)
        self.style().unpolish(self)
        self.style().polish(self)

    # --- Drag support ---

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_was_left = True
            sidebar = self._find_sidebar()
            if sidebar and sidebar._drag_ctrl:
                sidebar._drag_ctrl.on_press(self, event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        sidebar = self._find_sidebar()
        if sidebar and sidebar._drag_ctrl:
            sidebar._drag_ctrl.on_move(self, event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        sidebar = self._find_sidebar()
        if sidebar and sidebar._drag_ctrl:
            sidebar._drag_ctrl.on_release(self, event)
            # Only emit clicked if we didn't drag
            if not sidebar._drag_ctrl.is_dragging and getattr(self, '_press_was_left', False):
                self.clicked.emit(self._page_index)
        else:
            if getattr(self, '_press_was_left', False):
                self.clicked.emit(self._page_index)
        self._press_was_left = False
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:
        """Handle width changes to maintain perfect aspect ratio dynamically."""
        super().resizeEvent(event)
        
        # Avoid infinite layout loops by checking if width actually changed
        if event.oldSize().width() == event.size().width():
            return
            
        inner_w = event.size().width() - 8
        if inner_w <= 0:
            return
            
        if hasattr(self, '_original_pixmap') and not self._original_pixmap.isNull():
            inner_h = int(inner_w * (self._original_pixmap.height() / self._original_pixmap.width()))
            if self.height() != inner_h + 8:
                self.setFixedHeight(inner_h + 8)
                self._apply_pixmap()
        elif hasattr(self, '_aspect_ratio'):
            inner_h = int(inner_w / self._aspect_ratio)
            if self.height() != inner_h + 8:
                self.setFixedHeight(inner_h + 8)
                
        self._position_badge()
