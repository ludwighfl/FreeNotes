"""PDF Annotator – Entry Point."""

import sys
import ctypes

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# PySide6 handles High DPI automatically explicitly (PER_MONITOR_AWARE_V2)

ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FreeNotes")
QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

from ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Prevent PyInstaller from losing style plugins and looking completely different
    from styles.loader import load_stylesheet
    app.setStyleSheet(load_stylesheet())

    from ui.main_window import MainWindow

    window = MainWindow()
    window.showMaximized()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
