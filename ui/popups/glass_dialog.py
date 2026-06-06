from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from core.app_settings import AppSettings
from app.app_state import AppState
from utils.path_helpers import get_app_path
from ui.animations.pop_in import PopInAnimation


class GlassDialog(QDialog):
    """Base custom dialog with frosted glass style, frameless window, draggability,
    custom title bar, and app icon integration.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._drag_pos = QPoint()
        self._radius = 12

        # Base layout
        self._base_layout = QVBoxLayout(self)
        self._base_layout.setContentsMargins(16, 12, 16, 16)
        self._base_layout.setSpacing(12)

        # Title bar layout
        self._title_bar = QHBoxLayout()
        self._title_bar.setSpacing(8)

        # Title Text
        self._title_label = QLabel()
        self._title_label.setFont(QFont("Roboto", 11, QFont.Weight.Bold))
        self._title_bar.addWidget(self._title_label)

        self._title_bar.addStretch()

        # Custom Close Button
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self.reject)
        self._title_bar.addWidget(self._close_btn)

        self._base_layout.addLayout(self._title_bar)

        # Content Layout
        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(12)
        self._base_layout.addLayout(self._content_layout, 1)

        self._update_styles()
        AppState().theme_updated.connect(self._update_styles)

    def _update_styles(self) -> None:
        is_light = AppSettings.get_theme() == "light"
        text_color = "#333333" if is_light else "#e0e0e0"
        btn_hover_bg = "rgba(0, 0, 0, 15)" if is_light else "rgba(255, 255, 255, 15)"

        self._title_label.setStyleSheet(f"color: {text_color}; background: transparent;")
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
                color: {text_color};
                font-size: 11px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {btn_hover_bg};
            }}
        """)

    def setWindowTitle(self, title: str) -> None:
        super().setWindowTitle(title)
        self._title_label.setText(title)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            # Handle drag window logic
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def paintEvent(self, event) -> None:
        is_light = AppSettings.get_theme() == "light"
        if is_light:
            bg = QColor(245, 245, 245, 245)
            border = QColor(0, 0, 0, 30)
        else:
            bg = QColor(30, 30, 30, 245)
            border = QColor(255, 255, 255, 30)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self._radius, self._radius)
        painter.fillPath(path, bg)

        painter.setPen(QPen(border, 1.5))
        painter.drawPath(path)
        painter.end()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        PopInAnimation(self).start()
