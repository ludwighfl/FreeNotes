"""Main window – top-level QMainWindow with stacked ManagerView / ViewerWindow."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QShortcut, QKeySequence, QIcon, QFont
from PySide6.QtWidgets import (
    QMainWindow, QStackedWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog,
)

from app.app_state import AppState
from core import undo_stack
from core.app_settings import AppSettings
from core.library_manager import LibraryManager
from ui.manager_view import ManagerView
from ui.viewer_window import ViewerWindow
from utils.path_helpers import get_default_annotations_root


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

        from ui.splash_screen import SplashScreen
        from utils.path_helpers import get_app_path
        banner_path = get_app_path() / "assets" / "banner.png"
        self._splash_screen = SplashScreen(str(banner_path))

        self._stack.addWidget(self._manager_view)   # index 0
        self._stack.addWidget(self._viewer_window)   # index 1
        self._stack.addWidget(self._splash_screen)   # index 2

        # Connections
        self._manager_view.open_pdf_requested.connect(self.show_viewer)
        self._viewer_window.back_requested.connect(self.show_manager)

        # --- Keyboard shortcuts: Undo / Redo ---
        undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        undo_shortcut.activated.connect(self._handle_undo)

        redo_shortcut_y = QShortcut(QKeySequence("Ctrl+Y"), self)
        redo_shortcut_y.activated.connect(self._handle_redo)

        redo_shortcut_z = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        redo_shortcut_z.activated.connect(self._handle_redo)

        # Start on splash screen (index 2)
        self._stack.setCurrentIndex(2)
        QTimer.singleShot(5000, self._after_splash)

        # Enable drag & drop
        self.setAcceptDrops(True)

    # ------------------------------------------------------------------
    # First-run / library init
    # ------------------------------------------------------------------

    def _after_splash(self) -> None:
        """Called after splash timeout. Handles first-run or normal start."""
        if AppSettings.is_first_run():
            self._show_first_run_dialog()
        else:
            root = AppSettings.get_annotations_root()
            AppState().library_manager = LibraryManager(root)
        self.show_manager()

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
        self._stack.setCurrentIndex(0)

    def show_viewer(self, path: Path) -> None:
        """Switch to the viewer and open the given PDF.

        Args:
            path: Path to the PDF file to open.
        """
        self._viewer_window.open_pdf(path)
        self._stack.setCurrentIndex(1)

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

