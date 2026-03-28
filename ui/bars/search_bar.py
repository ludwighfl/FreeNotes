"""Floating search bar for the PDF viewer."""

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QBrush, QPen
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QToolButton,
    QGraphicsDropShadowEffect,
    QSizePolicy,
)

from ui.components.icon_factory import IconFactory


class SearchBar(QWidget):
    """Floating search bar shown at the top of the viewer via Ctrl+F."""

    search_changed = Signal(str)
    navigate_prev = Signal()
    navigate_next = Signal()
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("searchBar")
        self.setFixedHeight(44)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        # Search icon
        search_icon = QLabel()
        search_icon.setPixmap(
            IconFactory.create_pixmap("search", color="#666666", size=14))
        search_icon.setFixedSize(14, 14)
        search_icon.setStyleSheet("background: transparent;")
        layout.addWidget(search_icon)

        # Search input
        self._input = QLineEdit()
        self._input.setObjectName("searchInput")
        self._input.setPlaceholderText("Im PDF suchen …")
        self._input.setFixedHeight(30)
        self._input.setMinimumWidth(200)
        layout.addWidget(self._input)

        # Hit counter
        self._count_label = QLabel("")
        self._count_label.setObjectName("searchCount")
        self._count_label.setFixedWidth(90)
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._count_label)

        # Navigation: prev
        self._prev_btn = QToolButton()
        self._prev_btn.setIcon(
            IconFactory.create("chevron_up", color="#cccccc", size=16))
        self._prev_btn.setObjectName("searchNavBtn")
        self._prev_btn.setFixedSize(28, 28)
        self._prev_btn.setToolTip("Vorheriger Treffer")
        self._prev_btn.clicked.connect(self.navigate_prev)
        layout.addWidget(self._prev_btn)

        # Navigation: next
        self._next_btn = QToolButton()
        self._next_btn.setIcon(
            IconFactory.create("chevron_down", color="#cccccc", size=16))
        self._next_btn.setObjectName("searchNavBtn")
        self._next_btn.setFixedSize(28, 28)
        self._next_btn.setToolTip("Nächster Treffer")
        self._next_btn.clicked.connect(self.navigate_next)
        layout.addWidget(self._next_btn)

        # Close button
        close_btn = QToolButton()
        close_btn.setIcon(
            IconFactory.create("x", color="#cccccc", size=16))
        close_btn.setObjectName("searchCloseBtn")
        close_btn.setFixedSize(28, 28)
        close_btn.setToolTip("Schließen (Esc)")
        close_btn.clicked.connect(self._on_close)
        layout.addWidget(close_btn)

        # Debounce timer (300ms)
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._emit_search)
        self._input.textChanged.connect(
            lambda: self._search_timer.start())

        # Enter key navigates to next
        self._input.returnPressed.connect(self.navigate_next)

        self.hide()

    # ------------------------------------------------------------------

    def show_search(self) -> None:
        """Show and focus the search bar."""
        self._reposition()
        self.show()
        self.raise_()
        self._input.setFocus()
        self._input.selectAll()

    def _reposition(self) -> None:
        """Position in the top-right of the parent widget."""
        p = self.parent()
        if p:
            pw = p.width()
            self.setFixedWidth(min(420, pw - 40))
            x = pw - self.width() - 20
            y = 70  # Below toolbar
            self.move(x, y)

    def _on_close(self) -> None:
        self.hide()
        self._input.clear()
        self.closed.emit()

    def _emit_search(self) -> None:
        self.search_changed.emit(self._input.text())

    def update_count(self, current: int, total: int) -> None:
        """Update the hit counter display."""
        if total == 0:
            self._count_label.setText("")
            self._count_label.setStyleSheet(
                "color: #888888; background: transparent;")
        else:
            self._count_label.setText(f"{current + 1} / {total}")
            self._count_label.setStyleSheet(
                "color: #cccccc; background: transparent;")

    def keyPressEvent(self, event) -> None:
        """Handle Escape to close."""
        if event.key() == Qt.Key.Key_Escape:
            self._on_close()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Custom painting – rounded dark background
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor("#1e1e1e")))
        painter.setPen(QPen(QColor("#3a3a3a"), 1))
        painter.drawRoundedRect(
            self.rect().adjusted(0, 0, -1, -1), 8, 8)
