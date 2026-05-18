"""A single sidebar entry with icon and text."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

from ui.components.icon_factory import IconFactory
from core.app_settings import AppSettings


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
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("active", "false")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8 + indent * 16, 4, 8, 4)
        layout.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(16, 16)

        self._text_label = QLabel(text)
        self._text_label.setObjectName("sidebarItemText")

        layout.addWidget(self._icon_label)
        layout.addWidget(self._text_label, 1)

        self.setFixedHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_icon()

    def _update_icon(self) -> None:
        is_light = AppSettings.get_theme() == "light"
        if self._active:
            color = "#ffffff"
        else:
            color = "#333333" if is_light else "#cccccc"
        self._icon_label.setPixmap(
            IconFactory.create_pixmap(self._icon_name, color=color, size=16))

    def set_active(self, active: bool) -> None:
        """Set the active visual state of the sidebar item."""
        if self._active == active:
            return
        self._active = active
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self._update_icon()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit clicked signal when the item is clicked."""
        self.clicked.emit()
        super().mousePressEvent(event)
