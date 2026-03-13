"""Stylesheet loader – combines all QSS part files into one string."""

from pathlib import Path
from utils.path_helpers import get_app_path


def load_stylesheet() -> str:
    """
    Load all part stylesheets and return them as a merged string.
    Order matters: base → toolbar → formatting_bar → textbox.
    """
    style_dir = get_app_path() / "styles"
    parts = ["base", "toolbar", "formatting_bar", "textbox"]
    combined = []
    for part in parts:
        path = style_dir / f"{part}.qss"
        if path.exists():
            combined.append(f"/* ══ {part}.qss ══ */\n")
            combined.append(path.read_text(encoding="utf-8"))
            combined.append("\n")
    return "\n".join(combined)
