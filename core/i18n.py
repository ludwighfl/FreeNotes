"""Internationalization support for FreeNotes."""

import json
from pathlib import Path
from utils.path_helpers import get_app_path

_translations: dict[str, str] = {}
_current_lang: str = "de"

def init_i18n() -> None:
    """Load the translation dictionary based on AppSettings."""
    global _translations, _current_lang
    try:
        from core.app_settings import AppSettings
        _current_lang = AppSettings.get_language()
    except Exception:
        _current_lang = "de"

    file_path = get_app_path() / "i18n" / f"{_current_lang}.json"
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                _translations = json.load(f)
        except Exception as e:
            print(f"Failed to load translations from {file_path}: {e}")
            _translations = {}
    else:
        _translations = {}

def tr(key: str, default: str = "") -> str:
    """Translate a key to the current language."""
    return _translations.get(key, default or key)
