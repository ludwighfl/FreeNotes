"""A single sidebar entry with icon and text."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

from ui.icon_factory import IconFactory


class SidebarItem(QWidget):
    """A single sidebar entry with icon + text."""

    clicked = Signal()

    def __init__(
        self,
        icon_name: str,
        text: str,
        indent: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("sidebarItem")
        self._active = False
        self._icon_name = icon_name
        self._text = text

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8 + indent * 16, 4, 8, 4)
        layout.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setPixmap(
            IconFactory.create_pixmap(icon_name, color="#cccccc", size=16))
        self._icon_label.setFixedSize(16, 16)

        self._text_label = QLabel(text)
        self._text_label.setStyleSheet(
            "color: #cccccc; font-size: 13px; background: transparent;")

        layout.addWidget(self._icon_label)
        layout.addWidget(self._text_label, 1)

        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_active(self, active: bool) -> None:
        """Set the active visual state of the sidebar item."""
        self._active = active
        if active:
            self.setStyleSheet(
                "background: #3B7BF5; border-radius: 6px;")
            self._icon_label.setPixmap(
                IconFactory.create_pixmap(
                    self._icon_name, color="#ffffff", size=16))
            self._text_label.setStyleSheet(
                "color: #ffffff; font-size: 13px; background: transparent;")
        else:
            self.setStyleSheet("background: transparent;")
            self._icon_label.setPixmap(
                IconFactory.create_pixmap(
                    self._icon_name, color="#cccccc", size=16))
            self._text_label.setStyleSheet(
                "color: #cccccc; font-size: 13px; background: transparent;")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit clicked signal when the item is clicked."""
        self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event: object) -> None:
        """Show hover effect."""
        if not self._active:
            self.setStyleSheet(
                "background: #2d2d2d; border-radius: 6px;")
        super().enterEvent(event)

    def leaveEvent(self, event: object) -> None:
        """Remove hover effect."""
        if not self._active:
            self.setStyleSheet("background: transparent;")
        super().leaveEvent(event)
