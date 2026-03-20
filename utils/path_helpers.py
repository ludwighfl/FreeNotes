"""Path resolving utilities for handling PyInstaller MEIPASS."""

import os
import sys
from pathlib import Path


def get_app_path() -> Path:
    """
    Get absolute path to resource, works for dev and for PyInstaller.
    PyInstaller creates a temp folder and stores path in _MEIPASS.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    # Dev mode: assumes this file is in app_src/utils/path_helpers.py
    return Path(__file__).parent.parent


def get_default_annotations_root() -> Path:
    """Return the platform-specific default annotations root folder."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    return base / "FreeNotes" / "Annotations"
