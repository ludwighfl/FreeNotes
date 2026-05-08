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


class ThumbnailCard(QFrame):
    """Single thumbnail card: page image + page number badge."""

    clicked = Signal(int)

    THUMB_WIDTH: int = 160
    BADGE_COLOR: str = "#3B7BF5"
    ACTIVE_BORDER_COLOR: str = "#3B7BF5"

    def __init__(self, page_index: int, doc_manager=None, parent: QWidget | None = None) -> None:
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
        
        # Calculate proper placeholder aspect ratio
        height = int(self.THUMB_WIDTH * 1.414)
        if doc_manager is not None:
            w, h = doc_manager.get_page_size(page_index)
            if w > 0:
                height = int(self.THUMB_WIDTH * (h / w))
        self.setMinimumSize(self.THUMB_WIDTH, height)
        
        self._update_style()

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        """Set the thumbnail pixmap, scaled to THUMB_WIDTH with page badge."""
        if pixmap.isNull():
            return
            
        # Account for HiDPI: scale to logical width × actual screen devicePixelRatio
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        screen_dpr = app.primaryScreen().devicePixelRatio() if app and app.primaryScreen() else 1.0
        
        physical_width = int(self.THUMB_WIDTH * screen_dpr)
        scaled = pixmap.scaledToWidth(
            physical_width, Qt.TransformationMode.SmoothTransformation
        )
        scaled.setDevicePixelRatio(screen_dpr)
        self._scaled_pixmap = scaled  # keep for badge re-render
        self._render_badge()

        from ui.animations.thumbnail import ThumbnailFadeAnimation
        ThumbnailFadeAnimation(
            label=self._thumb_label,
            duration=200,
            parent=self,
        ).start()

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
