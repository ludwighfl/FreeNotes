"""Main window – top-level QMainWindow with stacked ManagerView / ViewerWindow."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence, QIcon
from PySide6.QtWidgets import QMainWindow, QStackedWidget

from core import undo_stack
from ui.manager_view import ManagerView
from ui.viewer_window import ViewerWindow


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
        from PySide6.QtCore import QTimer
        QTimer.singleShot(5000, self.show_manager)

        # Enable drag & drop
        self.setAcceptDrops(True)

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

