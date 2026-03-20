"""Manager view – file browser with folder sidebar and PDF card grid."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QFont, QAction
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QScrollArea,
    QGridLayout,
    QFrame,
    QLabel,
    QPushButton,
    QFileDialog,
    QMenu,
    QToolButton,
    QInputDialog,
    QMessageBox,
    QProgressDialog,
    QApplication,
)

from ui.icon_factory import IconFactory
from ui.sidebar_item import SidebarItem
from ui.pdf_card import PdfCard


class ManagerView(QWidget):
    """File manager screen with folder sidebar and PDF card grid."""

    open_pdf_requested = Signal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("managerView")
        self._cards: list[PdfCard] = []
        self._sidebar_items: list[SidebarItem] = []
        self._active_sidebar_item: SidebarItem | None = None
        self._expanded_folders: set[Path] = set()

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

        # Create button with dropdown
        create_btn = QToolButton()
        create_btn.setText("+ Erstellen")
        create_btn.setObjectName("createBtn")
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)

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
        settings_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)

        settings_menu = QMenu(settings_btn)
        settings_menu.setObjectName("settingsMenu")

        act_export_pdf = QAction(
            "Bibliothek als PDFs exportieren …", self)
        act_export_backup = QAction(
            "Bibliothek als Backup exportieren …", self)
        act_change_path = QAction(
            "Verzeichnis-Pfad ändern …", self)

        settings_menu.addAction(act_export_pdf)
        settings_menu.addAction(act_export_backup)
        settings_menu.addSeparator()
        settings_menu.addAction(act_change_path)
        settings_btn.setMenu(settings_menu)

        act_export_pdf.triggered.connect(
            lambda: self._on_export("pdf"))
        act_export_backup.triggered.connect(
            lambda: self._on_export("backup"))
        act_change_path.triggered.connect(self._on_change_path)
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

        # Init with library data if ready, or wait for signal
        from app.app_state import AppState
        if AppState().library_manager is not None:
            self.load_sidebar()
            self.load_folder(None)
        else:
            AppState().library_ready.connect(self._on_library_ready)

    def _on_library_ready(self) -> None:
        self.load_sidebar()
        self.load_folder(None)

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def load_sidebar(self) -> None:
        """Populate the folder sidebar from LibraryManager."""
        from app.app_state import AppState
        lm = AppState().library_manager
        if lm is None:
            return

        # Clear existing items
        for item in self._sidebar_items:
            self._sidebar_layout.removeWidget(item)
            item.deleteLater()
        self._sidebar_items.clear()
        self._active_sidebar_item = None

        # "Alle Dokumente"
        all_item = SidebarItem(
            icon_name="layout_grid", text="Alle Dokumente")
        all_item.clicked.connect(
            lambda: self._on_sidebar_clicked(None, all_item))
        self._sidebar_layout.insertWidget(
            self._sidebar_layout.count() - 1, all_item)
        self._sidebar_items.append(all_item)

        # "Zuletzt geöffnet"
        from core.app_settings import AppSettings
        if AppSettings.get_last_opened():
            recent_item = SidebarItem(
                icon_name="clock", text="Zuletzt geöffnet")
            recent_item.clicked.connect(
                lambda: self._on_sidebar_clicked("recent", recent_item))
            self._sidebar_layout.insertWidget(
                self._sidebar_layout.count() - 1, recent_item)
            self._sidebar_items.append(recent_item)

        # Recursive folder tree
        self._add_folders_to_sidebar(lm.root, depth=0)

        # Activate first item
        if self._sidebar_items:
            self._set_active_sidebar(self._sidebar_items[0])

    def _add_folders_to_sidebar(
        self, parent_folder: Path, depth: int
    ) -> None:
        """Recursively add folders and files to sidebar."""
        from app.app_state import AppState
        lm = AppState().library_manager
        if lm is None:
            return

        for subfolder in lm.get_folders(parent_folder):
            is_expanded = subfolder in self._expanded_folders
            icon = "folder_open" if is_expanded else "folder"
            chevron = "▼ " if is_expanded else "▶ "
            item = SidebarItem(
                icon_name=icon,
                text=f"{chevron}{subfolder.name}",
                indent=depth)
            item.clicked.connect(
                lambda f=subfolder, it=item: self._on_folder_toggled(f, it))
            self._sidebar_layout.insertWidget(
                self._sidebar_layout.count() - 1, item)
            self._sidebar_items.append(item)

            if is_expanded:
                # Show documents inside this folder
                for doc in lm.get_documents(subfolder):
                    doc_item = SidebarItem(
                        icon_name="file",
                        text=doc["name"],
                        indent=depth + 1)
                    doc_item.clicked.connect(
                        lambda d=doc: self._on_doc_sidebar_clicked(d))
                    self._sidebar_layout.insertWidget(
                        self._sidebar_layout.count() - 1, doc_item)
                    self._sidebar_items.append(doc_item)
                # Recurse into sub-folders
                self._add_folders_to_sidebar(subfolder, depth + 1)

    def _on_sidebar_clicked(
        self, data: object, item: SidebarItem
    ) -> None:
        self._set_active_sidebar(item)
        if data == "recent":
            self._load_recent_documents()
        else:
            self.load_folder(data)

    def _on_folder_toggled(
        self, folder: Path, item: SidebarItem
    ) -> None:
        if folder in self._expanded_folders:
            self._expanded_folders.discard(folder)
        else:
            self._expanded_folders.add(folder)
        self.load_sidebar()
        self.load_folder(folder)

    def _on_doc_sidebar_clicked(self, doc: dict) -> None:
        pdf_path = doc.get("pdf")
        if pdf_path and pdf_path.exists():
            fn = doc.get("freenotes")
            if fn:
                from core.app_settings import AppSettings
                AppSettings.add_last_opened(str(fn))
            self.open_pdf_requested.emit(pdf_path)

    def _set_active_sidebar(self, item: SidebarItem) -> None:
        if self._active_sidebar_item:
            self._active_sidebar_item.set_active(False)
        item.set_active(True)
        self._active_sidebar_item = item

    # ------------------------------------------------------------------
    # Grid loading
    # ------------------------------------------------------------------

    def load_folder(self, folder: Path | None) -> None:
        from app.app_state import AppState
        lm = AppState().library_manager
        if lm is None:
            return

        AppState().current_folder = folder
        target = folder or lm.root
        self._folder_title.setText(
            target.name if folder else "Alle Dokumente")

        self._clear_grid()
        docs = lm.get_documents(target)

        if not docs:
            self._show_empty_state()
            return

        self._hide_empty_state()
        for i, doc in enumerate(docs):
            card = PdfCard(
                pdf_path=doc["pdf"],
                freenotes_path=doc["freenotes"],
                name=doc["name"],
                modified=doc["modified"])
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

    def _load_recent_documents(self) -> None:
        from core.app_settings import AppSettings
        self._folder_title.setText("Zuletzt geöffnet")
        self._clear_grid()

        paths = AppSettings.get_last_opened()
        if not paths:
            self._show_empty_state()
            return

        self._hide_empty_state()
        for i, fn_path_str in enumerate(paths):
            fn_path = Path(fn_path_str)
            if not fn_path.exists():
                continue
            pdf_path = fn_path.with_suffix(".pdf")
            card = PdfCard(
                pdf_path=pdf_path if pdf_path.exists() else None,
                freenotes_path=fn_path,
                name=fn_path.stem,
                modified=fn_path.stat().st_mtime)
            card.double_clicked.connect(self._on_card_double_clicked)
            row = i // 4
            col = i % 4
            self._grid_layout.addWidget(card, row, col)
            self._cards.append(card)

        QTimer.singleShot(50, self._check_visible_cards)

    # ------------------------------------------------------------------
    # Grid helpers
    # ------------------------------------------------------------------

    def _clear_grid(self) -> None:
        for card in self._cards:
            self._grid_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    def _check_visible_cards(self) -> None:
        viewport_rect = self._scroll.viewport().rect()
        for card in self._cards:
            mapped = self._grid_container.mapTo(
                self._scroll.viewport(), card.geometry().topLeft())
            visible_rect = card.rect().translated(mapped)
            if viewport_rect.intersects(visible_rect):
                card.render_if_needed()

    def _show_empty_state(self) -> None:
        if not hasattr(self, "_empty_label"):
            self._empty_label = QLabel(
                "📂\n\nKeine Dokumente\n\n"
                "Importiere ein PDF über '+ Erstellen'")
            self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._empty_label.setStyleSheet(
                "color: #555555; font-size: 14px;")
            self._grid_layout.addWidget(self._empty_label, 0, 0, 1, 4)
        self._empty_label.setVisible(True)

    def _hide_empty_state(self) -> None:
        if hasattr(self, "_empty_label"):
            self._empty_label.setVisible(False)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

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
        self.load_folder(folder)
        self.load_sidebar()

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
            self.load_folder(AppState().current_folder)

    def _on_delete(self, doc: dict) -> None:
        from app.app_state import AppState
        lm = AppState().library_manager
        if lm:
            lm.delete_document(doc, trash=True)
            self.load_folder(AppState().current_folder)

    # ------------------------------------------------------------------
    # Export (direct from settings menu)
    # ------------------------------------------------------------------

    def _on_export(self, mode: str) -> None:
        from app.app_state import AppState
        lm = AppState().library_manager
        if lm is None:
            return

        target, _ = QFileDialog.getSaveFileName(
            self, "ZIP speichern unter", "",
            "ZIP-Archiv (*.zip)")
        if not target:
            return
        if not target.endswith(".zip"):
            target += ".zip"

        progress = QProgressDialog(
            "Exportiere …", "Abbrechen", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)
        progress.show()

        def on_progress(pct: int, name: str) -> None:
            progress.setValue(pct)
            progress.setLabelText(f"Exportiere: {name}")
            QApplication.processEvents()

        from core.zip_exporter import ZipExporter
        exporter = ZipExporter(lm)
        try:
            if mode == "pdf":
                exporter.export_annotated_pdfs(
                    Path(target), on_progress)
            else:
                exporter.export_backup(
                    Path(target), on_progress)
            progress.close()
            QMessageBox.information(
                self, "Export erfolgreich",
                f"ZIP gespeichert:\n{target}")
        except Exception as e:
            progress.close()
            QMessageBox.critical(
                self, "Export fehlgeschlagen", str(e))

    # ------------------------------------------------------------------
    # Change annotations path
    # ------------------------------------------------------------------

    def _on_change_path(self) -> None:
        from core.app_settings import AppSettings
        from core.library_manager import LibraryManager
        from app.app_state import AppState

        current = str(AppSettings.get_annotations_root() or "")
        chosen = QFileDialog.getExistingDirectory(
            self, "Neues Verzeichnis wählen", current)
        if not chosen:
            return

        reply = QMessageBox.question(
            self, "Verzeichnis ändern",
            f"FreeNotes verwendet ab jetzt:\n{chosen}\n\n"
            "Bestehende Dokumente werden nicht verschoben.",
            QMessageBox.StandardButton.Ok
            | QMessageBox.StandardButton.Cancel)
        if reply != QMessageBox.StandardButton.Ok:
            return

        new_root = Path(chosen)
        AppSettings.set_annotations_root(new_root)
        AppState().library_manager = LibraryManager(new_root)
        self.load_sidebar()
        self.load_folder(None)

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        self._lazy_timer.start()
