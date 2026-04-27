"""Settings view – full-screen settings panel with sidebar navigation."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QFrame,
    QLabel,
    QPushButton,
    QToolButton,
    QSizePolicy,
)

from ui.components.icon_factory import IconFactory
from core.i18n import tr


class SettingsView(QWidget):
    """Settings screen with sidebar navigation and stacked pages."""

    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("settingsView")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setObjectName("settingsHeader")
        header.setFixedHeight(56)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.setSpacing(12)

        back_btn = QPushButton()
        back_btn.setIcon(
            IconFactory.create("chevron_left", color="#cccccc", size=20))
        back_btn.setIconSize(QSize(20, 20))
        back_btn.setObjectName("backBtn")
        back_btn.setFixedSize(32, 32)
        back_btn.setToolTip(tr("settings.back"))
        back_btn.clicked.connect(self.back_requested)
        header_layout.addWidget(back_btn)

        title = QLabel(tr("settings.title"))
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setObjectName("settingsTitleLabel")
        header_layout.addWidget(title)
        header_layout.addStretch()
        main_layout.addWidget(header)

        # Horizontal separator
        hsep = QFrame()
        hsep.setFrameShape(QFrame.Shape.HLine)
        hsep.setObjectName("settingsSeparator")
        main_layout.addWidget(hsep)

        # ── Content: Sidebar + Stack ──
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._sidebar = self._build_sidebar()
        content_layout.addWidget(self._sidebar)

        vsep = QFrame()
        vsep.setFrameShape(QFrame.Shape.VLine)
        vsep.setObjectName("settingsSeparator")
        content_layout.addWidget(vsep)

        self._stack = QStackedWidget()
        self._stack.setObjectName("settingsStack")
        content_layout.addWidget(self._stack, 1)

        main_layout.addWidget(content, 1)

        # ── Placeholder pages ──
        self._pages: dict[str, QWidget] = {}
        self._page_keys: list[str] = [
            "display", "pen", "language", "library"]

        for key in self._page_keys:
            placeholder = QLabel(f"[{key} – wird geladen]")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setObjectName("settingsPlaceholder")
            self._pages[key] = placeholder
            self._stack.addWidget(placeholder)

        # Activate first page
        self._active_key: str = "display"
        self._set_active_page("display")

    # ------------------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("settingsSidebar")
        sidebar.setFixedWidth(200)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(4)

        self._sidebar_btns: dict[str, QToolButton] = {}

        entries = [
            ("display", "monitor", tr("settings.tabs.display")),
            ("pen", "pen", tr("settings.tabs.pen")),
            ("language", "globe", tr("settings.tabs.language")),
            ("library", "folder", tr("settings.tabs.library")),
        ]

        for key, icon_name, label in entries:
            btn = QToolButton()
            btn.setObjectName("settingsSidebarBtn")
            btn.setCheckable(True)
            btn.setToolButtonStyle(
                Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setIcon(
                IconFactory.create(icon_name, color="#cccccc", size=16))
            btn.setIconSize(QSize(16, 16))
            btn.setText(f"  {label}")
            btn.setFixedHeight(36)
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed)
            btn.clicked.connect(
                lambda checked, k=key: self._set_active_page(k))
            layout.addWidget(btn)
            self._sidebar_btns[key] = btn

        layout.addStretch()
        return sidebar

    # ------------------------------------------------------------------

    def _set_active_page(self, key: str) -> None:
        self._active_key = key
        for k, btn in self._sidebar_btns.items():
            btn.setChecked(k == key)
        page = self._pages.get(key)
        if page:
            self._stack.setCurrentWidget(page)

    def show_page(self, key: str = "display") -> None:
        """Switch to a specific page by key (callable from outside)."""
        if key in self._pages:
            self._set_active_page(key)

    def replace_page(self, key: str, widget: QWidget) -> None:
        """Replace a placeholder page with a real widget."""
        old = self._pages.get(key)
        if old:
            idx = self._stack.indexOf(old)
            self._stack.removeWidget(old)
            old.deleteLater()
        self._pages[key] = widget
        self._stack.insertWidget(
            self._page_keys.index(key), widget)
        if self._active_key == key:
            self._stack.setCurrentWidget(widget)
