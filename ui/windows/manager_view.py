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


class ManagerView(QWidget):
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

        # Header row
        header = QHBoxLayout()
        self._folder_title = QLabel("Alle Dokumente")
        self._folder_title.setFont(
            QFont("Segoe UI", 16, QFont.Weight.Bold))
        self._folder_title.setStyleSheet("color: #ffffff;")
        header.addWidget(self._folder_title)
        header.addStretch()

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
        header.addWidget(self._search_input)

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
        header.addWidget(create_btn)

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
        header.addWidget(settings_btn)

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
    # Sidebar – folders only
    # ------------------------------------------------------------------

    def load_sidebar(self) -> None:
        """Populate the folder sidebar from LibraryManager."""
        from app.app_state import AppState
        lm = AppState().library_manager
        if lm is None:
            return

        # Clear existing items
        for w in self._sidebar_widgets:
            self._sidebar_layout.removeWidget(w)
            w.deleteLater()
        self._sidebar_widgets.clear()

        # "Alle Dokumente"
        all_item = self._make_sidebar_item(
            icon_name="layout_grid",
            text="Alle Dokumente",
            indent=0,
            active=(self._active_folder is None
                    and self._active_mode != "recent"),
            on_click=lambda: self._select_folder(None))
        self._sidebar_layout.insertWidget(
            self._sidebar_layout.count() - 1, all_item)
        self._sidebar_widgets.append(all_item)

        # "Zuletzt geöffnet"
        from core.app_settings import AppSettings
        if AppSettings.get_last_opened():
            recent_item = self._make_sidebar_item(
                icon_name="clock",
                text="Zuletzt geöffnet",
                indent=0,
                active=(self._active_mode == "recent"),
                on_click=self._select_recent)
            self._sidebar_layout.insertWidget(
                self._sidebar_layout.count() - 1, recent_item)
            self._sidebar_widgets.append(recent_item)

        # Recursive folder tree
        self._add_folders_to_sidebar(lm.root, depth=0)

    def _add_folders_to_sidebar(
        self, parent: Path, depth: int
    ) -> None:
        from app.app_state import AppState
        lm = AppState().library_manager
        if lm is None:
            return

        for folder in lm.get_folders(parent):
            is_expanded = folder in self._expanded_folders
            is_active = folder == self._active_folder

            chevron = "▼ " if is_expanded else "▶ "
            icon_name = "folder_open" if is_expanded else "folder"

            item = self._make_sidebar_item(
                icon_name=icon_name,
                text=f"{chevron}{folder.name}",
                indent=depth,
                active=is_active,
                on_click=lambda f=folder: self._toggle_folder(f))
            self._sidebar_layout.insertWidget(
                self._sidebar_layout.count() - 1, item)
            self._sidebar_widgets.append(item)

            if is_expanded:
                self._add_folders_to_sidebar(folder, depth + 1)

    def _make_sidebar_item(
        self,
        icon_name: str,
        text: str,
        indent: int,
        active: bool,
        on_click: object,
    ) -> QWidget:
        """Create a clickable sidebar item widget."""
        item = QWidget()
        item.setObjectName("sidebarItem")
        item.setFixedHeight(32)
        item.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(item)
        layout.setContentsMargins(8 + indent * 16, 4, 8, 4)
        layout.setSpacing(8)

        icon_lbl = QLabel()
        color = "#ffffff" if active else "#cccccc"
        icon_lbl.setPixmap(
            IconFactory.create(icon_name, color=color, size=16).pixmap(16, 16))
        icon_lbl.setFixedSize(16, 16)
        icon_lbl.setStyleSheet("background: transparent;")

        text_lbl = QLabel(text)
        text_lbl.setStyleSheet(
            f"color: {'#ffffff' if active else '#cccccc'};"
            " font-size: 13px;"
            " background: transparent;")

        layout.addWidget(icon_lbl)
        layout.addWidget(text_lbl, 1)

        if active:
            item.setStyleSheet(
                "QWidget#sidebarItem {"
                " background: #3B7BF5;"
                " border-radius: 6px; }")
        else:
            item.setStyleSheet(
                "QWidget#sidebarItem {"
                " background: transparent;"
                " border-radius: 6px; }"
                "QWidget#sidebarItem:hover {"
                " background: #2d2d2d; }")

        item.mousePressEvent = lambda e, fn=on_click: fn()
        return item

    # ------------------------------------------------------------------
    # Sidebar actions
    # ------------------------------------------------------------------

    def _toggle_folder(self, folder: Path) -> None:
        if folder in self._expanded_folders:
            self._expanded_folders.discard(folder)
        else:
            self._expanded_folders.add(folder)
        self._select_folder(folder)

    def _select_folder(self, folder: Path | None) -> None:
        self._active_folder = folder
        self._active_mode = "folder"
        self.load_sidebar()
        self.load_grid(folder)

    def _select_recent(self) -> None:
        self._active_mode = "recent"
        self._active_folder = None
        self.load_sidebar()
        self._load_recent_grid()

    # ------------------------------------------------------------------
    # Grid – recursive loading
    # ------------------------------------------------------------------

    def load_grid(self, folder: Path | None) -> None:
        from app.app_state import AppState
        lm = AppState().library_manager
        if lm is None:
            return

        AppState().current_folder = folder

        if folder is None:
            self._folder_title.setText("Alle Dokumente")
        else:
            self._folder_title.setText(folder.name)

        docs = lm.get_documents_recursive(folder)
        self._search_input.clear()
        self._all_docs = docs
        self._display_docs(docs)

    def _display_docs(self, docs: list[dict]) -> None:
        self._clear_grid()

        if not docs:
            self._show_empty_state()
            return
        self._hide_empty_state()

        from PySide6.QtWidgets import QApplication

        for i, doc in enumerate(docs):
            if i % 5 == 0:
                QApplication.processEvents()

            card = PdfCard(
                pdf_path=doc["pdf"],
                freenotes_path=doc["freenotes"],
                name=doc["name"],
                modified=doc["modified"],
                thumbnail_cache=self._thumbnail_cache,
            )
            card.double_clicked.connect(self._on_card_double_clicked)
            card.rename_requested.connect(
                lambda name, d=doc: self._on_rename(d, name))
            card.delete_requested.connect(
                lambda d=doc: self._on_delete(d))
            row = i // 4
            col = i % 4
            self._grid_layout.addWidget(card, row, col)
            self._cards.append(card)

        QTimer.singleShot(50, self._check_visible_cards)

    def _load_recent_grid(self) -> None:
        from core.app_settings import AppSettings

        self._folder_title.setText("Zuletzt geöffnet")
        self._search_input.clear()

        paths = AppSettings.get_last_opened()
        docs: list[dict] = []
        for p_str in paths:
            p = Path(p_str)
            if not p.exists():
                continue
            pdf = p.with_suffix(".pdf")
            docs.append({
                "pdf": pdf if pdf.exists() else None,
                "freenotes": p,
                "name": p.stem,
                "modified": p.stat().st_mtime,
                "folder": p.parent,
            })
        self._all_docs = docs
        self._display_docs(docs)

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

    # ------------------------------------------------------------------
    # Grid helpers
    # ------------------------------------------------------------------

    def _clear_grid(self) -> None:
        for card in self._cards:
            self._grid_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    def _check_visible_cards(self) -> None:
        """Check which cards are visible and start progressive rendering."""
        if not self._cards:
            return
        viewport_rect = self._scroll.viewport().rect()
        vp_global = self._scroll.viewport().mapToGlobal(QPoint(0, 0))

        for card in self._cards:
            if card._rendered:
                continue
            card_global = card.mapToGlobal(QPoint(0, 0))
            rel = card_global - vp_global
            card_rect = card.rect().translated(rel.x(), rel.y())
            if viewport_rect.intersects(card_rect):
                card.render_if_needed()
                # Yield to event loop after each render for smooth UI
                QTimer.singleShot(0, self._check_visible_cards)
                return

    def _show_empty_state(self) -> None:
        if not hasattr(self, "_empty_container"):
            # Create overlay widget parented to scroll viewport
            self._empty_container = QWidget(self._scroll.viewport())
            self._empty_container.setObjectName("emptyState")
            self._empty_container.setStyleSheet(
                "QWidget#emptyState { background: transparent; }")
            empty_layout = QVBoxLayout(self._empty_container)
            empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.setSpacing(12)

            icon_lbl = QLabel()
            icon_lbl.setPixmap(
                IconFactory.create_pixmap(
                    "folder_x", color="#444444", size=64))
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setStyleSheet("background: transparent;")
            empty_layout.addWidget(icon_lbl)

            title_lbl = QLabel("Keine Dokumente")
            title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_lbl.setStyleSheet(
                "color: #555555; font-size: 18px; font-weight: bold;"
                " background: transparent;")
            empty_layout.addWidget(title_lbl)

            desc_lbl = QLabel("Importiere ein PDF über 'Erstellen'")
            desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc_lbl.setStyleSheet(
                "color: #444444; font-size: 13px;"
                " background: transparent;")
            empty_layout.addWidget(desc_lbl)
        # Size to fill the entire viewport and raise above grid
        vp = self._scroll.viewport()
        self._empty_container.setGeometry(vp.rect())
        self._empty_container.raise_()
        self._empty_container.setVisible(True)

    def _hide_empty_state(self) -> None:
        if hasattr(self, "_empty_container"):
            self._empty_container.setVisible(False)

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        self._lazy_timer.start()
        # Keep empty state centered on resize
        if hasattr(self, "_empty_container") and self._empty_container.isVisible():
            vp = self._scroll.viewport()
            self._empty_container.setGeometry(vp.rect())

    def _on_card_double_clicked(self, doc: dict) -> None:
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
        lm = AppState().library_manager
        if lm:
            lm.rename_document(doc, new_name)
            if doc.get("pdf"):
                self._thumbnail_cache.invalidate(doc["pdf"])
            self.load_grid(AppState().current_folder)

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


