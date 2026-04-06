"""Manager view – file browser with folder sidebar and PDF card grid."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize, QTimer, QPoint
from PySide6.QtGui import QFont, QAction
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QScrollArea,
    QGridLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QMenu,
    QToolButton,
    QInputDialog,
    QMessageBox,
)

from ui.components.icon_factory import IconFactory
from ui.components.pdf_card import PdfCard

from ui.windows.manager_action_bar_mixin import ManagerActionBarMixin
from ui.windows.manager_sidebar_mixin import ManagerSidebarMixin
from ui.windows.manager_grid_mixin import ManagerGridMixin


class ManagerView(QWidget, ManagerActionBarMixin, ManagerSidebarMixin, ManagerGridMixin):
    """File manager screen with folder sidebar and PDF card grid."""

    open_pdf_requested = Signal(Path)
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("managerView")
        self._cards: list[PdfCard] = []
        self._all_docs: list[dict] = []
        self._sidebar_widgets: list[QWidget] = []
        self._expanded_folders: set[Path] = set()
        self._active_folder: Path | None = None
        self._active_mode: str = "folder"  # "folder" | "recent"

        from core.thumbnail_cache import ThumbnailCache
        self._thumbnail_cache = ThumbnailCache()

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Folder sidebar ---
        sidebar = QWidget()
        sidebar.setObjectName("managerSidebar")
        sidebar.setFixedWidth(220)
        sidebar_outer = QVBoxLayout(sidebar)
        sidebar_outer.setContentsMargins(12, 16, 12, 12)
        sidebar_outer.setSpacing(4)

        title_label = QLabel("Notizen")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #ffffff;")
        sidebar_outer.addWidget(title_label)
        sidebar_outer.addSpacing(12)

        # Scrollable sidebar content
        self._sidebar_scroll = QScrollArea()
        self._sidebar_scroll.setWidgetResizable(True)
        self._sidebar_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._sidebar_scroll.setObjectName("sidebarScroll")
        self._sidebar_scroll.setStyleSheet(
            "QScrollArea#sidebarScroll { border: none; background: #242424; }")

        self._sidebar_container = QWidget()
        self._sidebar_container.setObjectName("sidebarContainer")
        self._sidebar_container.setStyleSheet("background: #242424;")
        self._sidebar_layout = QVBoxLayout(self._sidebar_container)
        self._sidebar_layout.setContentsMargins(0, 0, 0, 0)
        self._sidebar_layout.setSpacing(2)
        self._sidebar_layout.addStretch()
        self._sidebar_scroll.setWidget(self._sidebar_container)

        sidebar_outer.addWidget(self._sidebar_scroll)
        main_layout.addWidget(sidebar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("managerSeparator")
        main_layout.addWidget(sep)

        # --- Content area ---
        content_widget = QWidget()
        content_widget.setObjectName("managerContent")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 16, 20, 12)
        content_layout.setSpacing(12)

        # Header row using Mixin (it defines _folder_title)
        header = QHBoxLayout()
        self.init_action_bar(header)

        # Search input with Lucide icon
        self._search_input = QLineEdit()
        self._search_input.setObjectName("managerSearch")
        self._search_input.setPlaceholderText("Dokument suchen …")
        self._search_input.setFixedWidth(220)
        self._search_input.setFixedHeight(32)
        self._search_input.addAction(
            IconFactory.create("search", color="#666666", size=14),
            QLineEdit.ActionPosition.LeadingPosition)
        self._search_input.textChanged.connect(self._on_search_changed)
        self._default_header_right_layout.addWidget(self._search_input)

        # Create button with Lucide file_plus icon
        create_btn = QToolButton()
        create_btn.setIcon(
            IconFactory.create("file_plus", color="#ffffff", size=16))
        create_btn.setIconSize(QSize(16, 16))
        create_btn.setText(" Erstellen")
        create_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        create_btn.setObjectName("createBtn")
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)
        create_btn.setStyleSheet(
            create_btn.styleSheet()
            + " QToolButton::menu-indicator { image: none; }")

        create_menu = QMenu(create_btn)
        create_menu.setObjectName("pageContextMenu")
        act_import = QAction("PDF importieren", self)
        act_folder = QAction("Neuer Ordner", self)
        create_menu.addAction(act_import)
        create_menu.addAction(act_folder)
        create_btn.setMenu(create_menu)

        act_import.triggered.connect(self._on_import_pdf)
        act_folder.triggered.connect(self._on_create_folder)
        self._default_header_right_layout.addWidget(create_btn)

        # Multi Select toggle button
        multi_select_btn = QToolButton()
        multi_select_btn.setIcon(
            IconFactory.create("check_square", color="#cccccc", size=20))
        multi_select_btn.setIconSize(QSize(20, 20))
        multi_select_btn.setObjectName("multiSelectBtn")
        multi_select_btn.setFixedSize(36, 36)
        multi_select_btn.setToolTip("Mehrfachauswahl umschalten")
        multi_select_btn.clicked.connect(self.toggle_multi_select)
        self._default_header_right_layout.addWidget(multi_select_btn)

        # Settings button (gear)
        settings_btn = QToolButton()
        settings_btn.setIcon(
            IconFactory.create("settings", color="#cccccc", size=20))
        settings_btn.setIconSize(QSize(20, 20))
        settings_btn.setObjectName("settingsBtn")
        settings_btn.setFixedSize(36, 36)
        settings_btn.setToolTip("Einstellungen")
        settings_btn.clicked.connect(
            self.settings_requested.emit)
        self._default_header_right_layout.addWidget(settings_btn)

        content_layout.addLayout(header)

        # Grid scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setObjectName("managerScroll")

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(16)
        self._grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._scroll.setWidget(self._grid_container)

        content_layout.addWidget(self._scroll)
        main_layout.addWidget(content_widget, 1)

        # Lazy-load timer
        self._lazy_timer = QTimer(self)
        self._lazy_timer.setInterval(100)
        self._lazy_timer.setSingleShot(True)
        self._lazy_timer.timeout.connect(self._check_visible_cards)
        self._scroll.verticalScrollBar().valueChanged.connect(
            lambda: self._lazy_timer.start())

        # Init with library data if ready
        from app.app_state import AppState
        if AppState().library_manager is not None:
            self.load_sidebar()
            self._select_folder(None)
        else:
            AppState().library_ready.connect(self._on_library_ready)

    def _on_library_ready(self) -> None:
        self.load_sidebar()
        self._select_folder(None)

    # ------------------------------------------------------------------
    # Live search
    # ------------------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        if not text.strip():
            self._display_docs(self._all_docs)
            return
        query = text.strip().lower()
        filtered = [d for d in self._all_docs if query in d["name"].lower()]
        self._display_docs(filtered)

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        self._lazy_timer.start()
        # Keep empty state centered on resize
        if hasattr(self, "_empty_container") and self._empty_container.isVisible():
            vp = self._scroll.viewport()
            self._empty_container.setGeometry(vp.rect())

    def _on_card_double_clicked(self, doc: dict) -> None:
        if hasattr(self, "clear_selection"):
            self.clear_selection()
            
        pdf_path = doc.get("pdf")
        if pdf_path and pdf_path.exists():
            fn = doc.get("freenotes")
            if fn:
                from core.app_settings import AppSettings
                AppSettings.add_last_opened(str(fn))
            self.open_pdf_requested.emit(pdf_path)

    def _on_import_pdf(self) -> None:
        from app.app_state import AppState
        files, _ = QFileDialog.getOpenFileNames(
            self, "PDF importieren", "", "PDF Dateien (*.pdf)")
        if not files:
            return
        lm = AppState().library_manager
        folder = AppState().current_folder
        for f in files:
            lm.import_pdf(Path(f), folder)
        self._select_folder(folder)

    def _on_create_folder(self) -> None:
        from app.app_state import AppState
        name, ok = QInputDialog.getText(
            self, "Neuer Ordner", "Ordnername:", text="Neuer Ordner")
        if not ok or not name.strip():
            return
        lm = AppState().library_manager
        parent = AppState().current_folder
        lm.create_folder(name.strip(), parent)
        self.load_sidebar()

    def _on_rename(self, doc: dict, new_name: str) -> None:
        from app.app_state import AppState
        app_state = AppState()
        lm = app_state.library_manager
        if lm:
            was_open = app_state.current_pdf_path and doc.get("pdf") and app_state.current_pdf_path.resolve() == doc["pdf"].resolve()
            
            new_doc = lm.rename_document(doc, new_name)
            
            if was_open:
                app_state.current_pdf_path = new_doc.get("pdf")
                if new_doc.get("freenotes"):
                    app_state.freenotes_path = str(new_doc["freenotes"])
                app_state.document_renamed.emit()
                
            if new_doc.get("pdf"):
                self._thumbnail_cache.invalidate(new_doc["pdf"])
            self.load_grid(app_state.current_folder)

    def _on_delete(self, doc: dict) -> None:
        from app.app_state import AppState
        lm = AppState().library_manager
        if lm:
            lm.delete_document(doc, trash=True)
            if doc.get("pdf"):
                self._thumbnail_cache.invalidate(doc["pdf"])
            self.load_grid(AppState().current_folder)

    # Backward compatibility alias
    def load_folder(self, folder: Path | None) -> None:
        """Alias for load_grid (backward compatibility)."""
        self.load_grid(folder)




