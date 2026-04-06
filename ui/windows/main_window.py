"""Main window – top-level QMainWindow with stacked ManagerView / ViewerWindow.

Startup sequence
----------------
1. __init__ creates only the splash overlay + central stack (fast, ~50 ms).
2. showMaximized() is called by main.py → window appears with splash.
3. Event loop starts → QTimer(0) fires → _build_ui() creates views one by one
   with processEvents() between each, so the splash animates smoothly.
4. After views are ready, _perform_startup_loading() launches the background
   StartupWorker thread for library scanning.
5. When both the worker AND the 2500 ms minimum splash time have elapsed,
   _finish_startup() loads the last document, hides the splash, and shows the
   target view.
"""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QShortcut, QKeySequence, QIcon, QFont
from PySide6.QtWidgets import (
    QMainWindow, QStackedWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QApplication,
)

from app.app_state import AppState
from core import undo_stack
from core.app_settings import AppSettings
from core.library_manager import LibraryManager
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
    Index 2: SettingsView
    """

    def __init__(self) -> None:
        super().__init__()
        import time
        self._start_time = time.time()
        self._splash_proc = None

        self.setWindowTitle("FreeNotes")

        icon_path = get_app_path() / "assets" / "icon.ico"
        self.setWindowIcon(QIcon(str(icon_path)))

        self.setMinimumSize(1024, 700)
        self.resize(1280, 800)

        # Central stack
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        from ui.animations import StackFadeTransition
        self._stack_transition = StackFadeTransition(self._stack, duration=150)

        from ui.windows.manager_view import ManagerView
        from ui.windows.viewer_window import ViewerWindow
        from ui.windows.settings_view import SettingsView

        self._manager_view = ManagerView()
        self._viewer_window = ViewerWindow()
        self._settings_view = SettingsView()
        self._load_settings_pages()

        self._stack.addWidget(self._manager_view)    # index 0
        self._stack.addWidget(self._viewer_window)   # index 1
        self._stack.addWidget(self._settings_view)   # index 2
        self._stack.setCurrentIndex(0)

        # Connections
        self._manager_view.open_pdf_requested.connect(self.show_viewer)
        self._manager_view.settings_requested.connect(self.show_settings)
        self._viewer_window.back_requested.connect(self.show_manager)
        self._settings_view.back_requested.connect(self.show_manager)

        # Keyboard shortcuts
        undo_sc = QShortcut(QKeySequence.StandardKey.Undo, self)
        undo_sc.activated.connect(self._handle_undo)
        redo_y = QShortcut(QKeySequence("Ctrl+Y"), self)
        redo_y.activated.connect(self._handle_redo)
        redo_z = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        redo_z.activated.connect(self._handle_redo)

        self.setAcceptDrops(True)

        self._perform_startup_loading()

    def set_splash_process(self, proc) -> None:
        """Store the external splash screen subprocess to terminate it later."""
        self._splash_proc = proc


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

    def _on_worker_finished(self) -> None:
        """Worker done. Ensure minimum splash time has elapsed before showing UI."""
        import time
        elapsed = time.time() - self._start_time
        remaining = max(0, 2.5 - elapsed)
        
        if remaining > 0:
            QTimer.singleShot(int(remaining * 1000), self._finish_startup)
        else:
            self._finish_startup()

    def _finish_startup(self, is_first_run: bool = False) -> None:
        """All conditions met. Load data, hide splash, show target view."""

        if is_first_run:
            self._dismiss_splash()
            self._show_first_run_dialog()
            return

        # Build manager grid (splash still animating)
        docs = getattr(AppState(), "_cached_startup_docs", [])
        self._manager_view._all_docs = docs
        self._manager_view._display_docs(docs)

        # Open last document if available, but only if viewer was active
        target_index = 0
        if AppSettings.get_last_active_view() == "viewer":
            last_doc = AppSettings.get_last_opened_doc()
            if last_doc:
                last_path = Path(last_doc)
                if last_path.exists():
                    if last_path.suffix == ".freenotes":
                        self._viewer_window.open_freenotes(str(last_path))
                        target_index = 1
                    elif last_path.suffix == ".pdf":
                        self._viewer_window.open_pdf(last_path)
                        target_index = 1

        self._stack.setCurrentIndex(target_index)
        self._dismiss_splash()

    def _dismiss_splash(self) -> None:
        """Kill the external splash process and reveal the main window."""
        if self._splash_proc:
            self._splash_proc.terminate()
            self._splash_proc = None
        
        self.showMaximized()

    # ------------------------------------------------------------------
    # First-run dialog
    # ------------------------------------------------------------------

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

    def show_manager(self, closed_path: Path | None = None) -> None:
        """Switch to the file manager view."""
        if closed_path and hasattr(self._manager_view, '_thumbnail_cache'):
            self._manager_view._thumbnail_cache.invalidate(closed_path)
            
        # Clean up visual state immediately before the crossfade pixel snapshot
        if hasattr(self._manager_view, "_multi_select_mode"):
            self._manager_view._multi_select_mode = False
            for card in getattr(self._manager_view, "_cards", []):
                if hasattr(card, "set_checkbox_visible"):
                    card.set_checkbox_visible(False)
        if hasattr(self._manager_view, "clear_selection"):
            self._manager_view.clear_selection()
            
        self._stack_transition.switch_to(0)
        # Yield to event loop to allow cross-fade animation to render smoothly
        QTimer.singleShot(150, lambda: self._manager_view.load_grid(AppState().current_folder))

    def show_viewer(self, path: Path) -> None:
        """Switch to the viewer and open the given PDF.

        Args:
            path: Path to the PDF file to open.
        """
        self._viewer_window.clear_ui()
        self._stack_transition.switch_to(1)
        # Yield to event loop to allow cross-fade animation to render smoothly
        QTimer.singleShot(150, lambda: self._viewer_window.open_pdf(path))

    def closeEvent(self, event: object) -> None:
        """Save settings before window closes."""
        current_index = self._stack.currentIndex()
        if current_index == 1:
            AppSettings.set_last_active_view("viewer")
        else:
            AppSettings.set_last_active_view("manager")
        super().closeEvent(event)

    def show_settings(self, page: str = "display") -> None:
        """Switch to the settings screen."""
        self._settings_view.show_page(page)
        self._stack_transition.switch_to(2)

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
