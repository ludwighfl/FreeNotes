"""PDF Annotator – Entry Point."""

import sys
import ctypes

import fitz
fitz.TOOLS.mupdf_display_errors(False)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# PySide6 handles High DPI automatically explicitly (PER_MONITOR_AWARE_V2)

ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FreeNotes")
QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

def run_splash_process() -> None:
    """Run the standalone splash screen process."""
    app = QApplication(sys.argv)
    from utils.path_helpers import get_app_path
    from ui.windows.splash_screen import SplashScreen
    
    banner_path = get_app_path() / "assets" / "banner.png"
    splash = SplashScreen(str(banner_path))
    splash.show()
    splash.start_animation()
    
    sys.exit(app.exec())


def main() -> None:
    if "--splash" in sys.argv:
        run_splash_process()
        return

    # Start the splash screen as a separate, fully decoupled OS process.
    import subprocess
    splash_proc = subprocess.Popen([sys.executable, sys.argv[0], "--splash"])

    app = QApplication(sys.argv)
    app.setDoubleClickInterval(300)
    app.setStyle("Fusion") # Prevent PyInstaller from losing style plugins
    from styles.loader import load_stylesheet
    app.setStyleSheet(load_stylesheet())

    # Build the heavy main application
    from ui.windows.main_window import MainWindow
    window = MainWindow()
    
    # We pass the splash_proc to MainWindow so it can kill it once fully ready
    # and the minimum display time has passed.
    window.set_splash_process(splash_proc)
    
    # window is NOT shown here. It will be shown by MainWindow._dismiss_splash()
    # once minimum display time has elapsed.

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
