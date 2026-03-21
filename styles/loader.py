"""Stylesheet loader – combines all QSS part files into one string."""

from pathlib import Path
from utils.path_helpers import get_app_path


def load_stylesheet() -> str:
    """
    Load all part stylesheets and return them as a merged string.
    Uses ``_light`` variants when the persisted theme is "light".
    Order matters: base → toolbar → formatting_bar → textbox.
    """
    from core.app_settings import AppSettings
    theme = AppSettings.get_theme()  # "dark" or "light"
    suffix = "_light" if theme == "light" else ""

    style_dir = get_app_path() / "styles"
    parts = ["base", "toolbar", "formatting_bar", "textbox"]
    combined = []
    for part in parts:
        # Try themed variant first, fall back to default
        path = style_dir / f"{part}{suffix}.qss"
        if not path.exists():
            path = style_dir / f"{part}.qss"
        if path.exists():
            combined.append(f"/* ══ {part}{suffix}.qss ══ */\n")
            combined.append(path.read_text(encoding="utf-8"))
            combined.append("\n")
    return "\n".join(combined)
