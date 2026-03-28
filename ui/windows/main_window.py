"""Main window – top-level QMainWindow with stacked ManagerView / ViewerWindow."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QShortcut, QKeySequence, QIcon, QFont
from PySide6.QtWidgets import (
    QMainWindow, QStackedWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog,
)

from app.app_state import AppState
from core import undo_stack
from core.app_settings import AppSettings
from core.library_manager import LibraryManager
from ui.windows.manager_view import ManagerView
from ui.windows.settings_view import SettingsView
from ui.windows.viewer_window import ViewerWindow
from ui.windows.splash_screen import SplashScreen
from utils.path_helpers import get_app_path, get_default_annotations_root

class StartupWorker(QThread):
    """Background worker to handle file system operations without freezing UI."""
    finished_loading = Signal()

    def run(self):
        root = AppSettings.get_annotations_root()
        from core.library_manager import LibraryManager
        AppState().library_manager = LibraryManager(root)
        
        folder = AppState().current_folder
        docs = AppState().library_manager.get_documents_recursive(folder)
        setattr(AppState(), "_cached_startup_docs", docs)

        self.finished_loading.emit()

class MainWindow(QMainWindow):
    """Application main window using QStackedWidget.

    Index 0: ManagerView (file browser)
    Index 1: ViewerWindow (PDF viewer)
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FreeNotes")

        from utils.path_helpers import get_app_path
        icon_path = get_app_path() / "assets" / "icon.ico"
        self.setWindowIcon(QIcon(str(icon_path)))

        self.setMinimumSize(1024, 700)
        self.resize(1280, 800)

        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Pages
        self._manager_view = ManagerView()
        self._viewer_window = ViewerWindow()

        from ui.windows.splash_screen import SplashScreen
        from utils.path_helpers import get_app_path
        banner_path = get_app_path() / "assets" / "banner.png"
        self._splash_screen = SplashScreen(str(banner_path))
        self._settings_view = SettingsView()
        self._load_settings_pages()

        self._stack.addWidget(self._manager_view)   # index 0
        self._stack.addWidget(self._viewer_window)   # index 1
        self._stack.addWidget(self._splash_screen)   # index 2
        self._stack.addWidget(self._settings_view)   # index 3

        # Connections
        self._manager_view.open_pdf_requested.connect(self.show_viewer)
        self._manager_view.settings_requested.connect(self.show_settings)
        self._viewer_window.back_requested.connect(self.show_manager)
        self._settings_view.back_requested.connect(self.show_manager)

        # --- Keyboard shortcuts: Undo / Redo ---
        undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        undo_shortcut.activated.connect(self._handle_undo)

        redo_shortcut_y = QShortcut(QKeySequence("Ctrl+Y"), self)
        redo_shortcut_y.activated.connect(self._handle_redo)

        redo_shortcut_z = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        redo_shortcut_z.activated.connect(self._handle_redo)

        # Start on splash screen (index 2)
        self._stack.setCurrentIndex(2)
        
        import time
        self._startup_time = time.time()
        # Wait 400ms so the window has time to show and start rendering the splash screen
        QTimer.singleShot(400, self._perform_startup_loading)

        # Enable drag & drop
        self.setAcceptDrops(True)

    # ------------------------------------------------------------------
    # Settings pages
    # ------------------------------------------------------------------

    def _load_settings_pages(self) -> None:
        """Replace placeholder pages in SettingsView with real content."""
        from ui.windows.settings_pages.display_page import DisplayPage
        from ui.windows.settings_pages.pen_page import PenPage
        from ui.windows.settings_pages.language_page import LanguagePage
        from ui.windows.settings_pages.library_page import LibraryPage

        self._settings_view.replace_page("display", DisplayPage())
        self._settings_view.replace_page("pen", PenPage())
        self._settings_view.replace_page("language", LanguagePage())
        self._settings_view.replace_page("library", LibraryPage())

    # ------------------------------------------------------------------
    # First-run / library init
    # ------------------------------------------------------------------

    def _perform_startup_loading(self) -> None:
        """Loads library and last document off the main thread."""
        if AppSettings.is_first_run():
            self._finish_startup(is_first_run=True)
            return

        # Start background worker for heavy disk I/O
        self._worker = StartupWorker()
        self._worker.finished_loading.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_finished(self):
        # We are back on the main thread. Apply UI.
        docs = getattr(AppState(), "_cached_startup_docs", [])
        self._manager_view._all_docs = docs
        self._manager_view._display_docs(docs)
        self._target_index = 0
        
        last_doc = AppSettings.get_last_opened_doc()
        if last_doc:
            last_path = Path(last_doc)
            if last_path.exists():
                if last_path.suffix == ".freenotes":
                    self._viewer_window.open_freenotes(str(last_path))
                    self._target_index = 1
                elif last_path.suffix == ".pdf":
                    self._viewer_window.open_pdf(last_path)
                    self._target_index = 1

        import time
        elapsed_ms = int((time.time() - self._startup_time) * 1000)
        min_duration_ms = 2500  # 2.5 seconds minimum
        
        remaining_ms = max(0, min_duration_ms - elapsed_ms)
        
        if remaining_ms > 0:
            QTimer.singleShot(remaining_ms, self._finish_startup)
        else:
            self._finish_startup()

    def _finish_startup(self, is_first_run: bool = False) -> None:
        """Finalizes startup by hiding splash screen and showing target view."""
        self._splash_screen.stop_animation()
        
        if is_first_run:
            self._stack.setCurrentIndex(0)
            self._show_first_run_dialog()
            return

        self._stack.setCurrentIndex(getattr(self, "_target_index", 0))

    def _show_first_run_dialog(self) -> None:
        """Show welcome dialog to choose annotations root folder."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Willkommen bei FreeNotes")
        dialog.setFixedSize(480, 280)
        dialog.setObjectName("firstRunDialog")

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(32, 32, 32, 24)
        layout.setSpacing(16)

        title = QLabel("Willkommen bei FreeNotes")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff;")
        layout.addWidget(title)

        desc = QLabel(
            "Wähle einen Ordner, in dem FreeNotes "
            "deine Dokumente und Annotationen speichert."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #aaaaaa; font-size: 13px;")
        layout.addWidget(desc)

        # Path row
        path_row = QHBoxLayout()
        default_root = get_default_annotations_root()
        self._first_run_path = default_root

        self._path_label = QLabel(str(default_root))
        self._path_label.setStyleSheet(
            "color: #cccccc; font-size: 12px; "
            "background: #2a2a2a; padding: 6px; "
            "border-radius: 4px;"
        )
        self._path_label.setWordWrap(True)
        path_row.addWidget(self._path_label, 1)

        browse_btn = QPushButton("Ändern")
        browse_btn.setObjectName("browseBtn")
        browse_btn.clicked.connect(lambda: self._browse_root(dialog))
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        layout.addStretch()

        ok_btn = QPushButton("Los geht's")
        ok_btn.setObjectName("primaryBtn")
        ok_btn.setFixedHeight(40)
        ok_btn.clicked.connect(dialog.accept)
        layout.addWidget(ok_btn)

        # Style the dialog
        dialog.setStyleSheet("""
            #firstRunDialog { background: #1e1e1e; }
            #browseBtn {
                background: #333333; color: #cccccc;
                border: 1px solid #444; border-radius: 4px;
                padding: 6px 12px;
            }
            #browseBtn:hover { background: #444444; }
            #primaryBtn {
                background: #3B7BF5; color: #ffffff;
                border: none; border-radius: 6px;
                font-size: 14px; font-weight: bold;
            }
            #primaryBtn:hover { background: #5090FF; }
        """)

        dialog.exec()

        # Save settings
        AppSettings.set_annotations_root(self._first_run_path)
        AppState().library_manager = LibraryManager(self._first_run_path)

    def _browse_root(self, dialog: QDialog) -> None:
        """Open folder picker for annotations root."""
        chosen = QFileDialog.getExistingDirectory(
            dialog,
            "Annotations-Ordner wählen",
            str(self._first_run_path),
        )
        if chosen:
            self._first_run_path = Path(chosen)
            self._path_label.setText(chosen)

    # ------------------------------------------------------------------
    # Undo / Redo
    # ------------------------------------------------------------------

    def _handle_undo(self) -> None:
        undo_stack.undo()

    def _handle_redo(self) -> None:
        undo_stack.redo()

    def show_manager(self) -> None:
        """Switch to the file manager view."""
        self._manager_view.load_grid(AppState().current_folder)
        self._stack.setCurrentIndex(0)

    def show_viewer(self, path: Path) -> None:
        """Switch to the viewer and open the given PDF.

        Args:
            path: Path to the PDF file to open.
        """
        self._viewer_window.open_pdf(path)
        self._stack.setCurrentIndex(1)

    def show_settings(self, page: str = "display") -> None:
        """Switch to the settings screen."""
        self._settings_view.show_page(page)
        self._stack.setCurrentIndex(3)

    # ------------------------------------------------------------------
    # Drag & Drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event: object) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: object) -> None:
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(".pdf"):
                self.show_viewer(Path(file_path))
                break

