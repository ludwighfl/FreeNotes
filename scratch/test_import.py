import sys
import os
import traceback
from PySide6.QtWidgets import QApplication

# Add the project root to sys.path
sys.path.append(os.getcwd())

app = QApplication(sys.argv)

try:
    from ui.windows.main_window import MainWindow
    print("Import successful. Instantiating MainWindow...")
    window = MainWindow()
    print("MainWindow instantiated successfully")
except Exception as e:
    traceback.print_exc()
    sys.exit(1)
