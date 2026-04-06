"""Persistent application settings via QSettings."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings


class AppSettings:
    """Singleton-like class for persistent app settings via QSettings."""

    ORGANIZATION = "FreeNotes"
    APPLICATION = "FreeNotes"

    @classmethod
    def _get(cls) -> QSettings:
        return QSettings(cls.ORGANIZATION, cls.APPLICATION)

    @classmethod
    def get_annotations_root(cls) -> Path | None:
        """Return the stored annotations root path, or None if unset."""
        s = cls._get()
        val = s.value("annotations_root", None)
        if val and Path(val).exists():
            return Path(val)
        return None

    @classmethod
    def set_annotations_root(cls, path: Path) -> None:
        """Persist the annotations root path."""
        cls._get().setValue("annotations_root", str(path))

    @classmethod
    def get_last_opened(cls) -> list[str]:
        """Return list of recently opened .freenotes paths (newest first)."""
        s = cls._get()
        val = s.value("last_opened", [])
        return val if isinstance(val, list) else []

    @classmethod
    def add_last_opened(cls, path: str) -> None:
        """Add a path to the recently-opened list (max 10, newest first)."""
        entries = cls.get_last_opened()
        if path in entries:
            entries.remove(path)
        entries.insert(0, path)
        cls._get().setValue("last_opened", entries[:10])

    @classmethod
    def is_first_run(cls) -> bool:
        """True if no annotations root has been configured yet."""
        return cls.get_annotations_root() is None

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    @classmethod
    def get_theme(cls) -> str:
        return cls._get().value("theme", "dark")

    @classmethod
    def set_theme(cls, theme: str) -> None:
        cls._get().setValue("theme", theme)

    # ------------------------------------------------------------------
    # Default font size
    # ------------------------------------------------------------------

    @classmethod
    def get_default_font_size(cls) -> int:
        return int(cls._get().value("default_font_size", 12))

    @classmethod
    def set_default_font_size(cls, size: int) -> None:
        cls._get().setValue("default_font_size", size)

    # ------------------------------------------------------------------
    # Pen
    # ------------------------------------------------------------------

    @classmethod
    def get_pen_colors(cls) -> list[str]:
        defaults = [
            "#1a1a1a", "#555555", "#aaaaaa", "#ffffff",
            "#3B7BF5", "#e53935", "#43a047", "#fdd835",
            "#00bcd4", "#6d4c41",
        ]
        val = cls._get().value("pen_colors", defaults)
        return val if isinstance(val, list) else defaults

    @classmethod
    def set_pen_colors(cls, colors: list[str]) -> None:
        cls._get().setValue("pen_colors", colors)

    @classmethod
    def get_pen_default_color(cls) -> str:
        return cls._get().value("pen_default_color", "#1a1a1a")

    @classmethod
    def set_pen_default_color(cls, color: str) -> None:
        cls._get().setValue("pen_default_color", color)

    @classmethod
    def get_pen_width(cls) -> float:
        return float(cls._get().value("pen_width", 3.0))

    @classmethod
    def set_pen_width(cls, width: float) -> None:
        cls._get().setValue("pen_width", width)

    # ------------------------------------------------------------------
    # Toolbar state
    # ------------------------------------------------------------------

    @classmethod
    def get_tool_memory(cls) -> dict:
        import json
        val = cls._get().value("tool_memory", None)
        if val:
            try:
                return json.loads(val)
            except Exception:
                pass
        return {}

    @classmethod
    def set_tool_memory(cls, memory: dict) -> None:
        import json
        cls._get().setValue("tool_memory", json.dumps(memory))

    @classmethod
    def get_active_tool(cls) -> str:
        return cls._get().value("active_tool", "hand")

    @classmethod
    def set_active_tool(cls, tool: str) -> None:
        cls._get().setValue("active_tool", tool)

    @classmethod
    def get_eraser_mode(cls) -> str:
        return cls._get().value("eraser_mode", "object")

    @classmethod
    def set_eraser_mode(cls, mode: str) -> None:
        cls._get().setValue("eraser_mode", mode)

    @classmethod
    def get_selection_mode(cls) -> str:
        return cls._get().value("selection_mode", "rect")

    @classmethod
    def set_selection_mode(cls, mode: str) -> None:
        cls._get().setValue("selection_mode", mode)

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------

    @classmethod
    def get_language(cls) -> str:
        return cls._get().value("language", "de")

    @classmethod
    def set_language(cls, code: str) -> None:
        cls._get().setValue("language", code)

    # ------------------------------------------------------------------
    # Per-PDF zoom
    # ------------------------------------------------------------------

    @classmethod
    def get_zoom(cls, pdf_path: str) -> float | None:
        import hashlib
        key = "zoom_" + hashlib.md5(pdf_path.encode()).hexdigest()[:8]
        val = cls._get().value(key, None)
        return float(val) if val is not None else None

    @classmethod
    def set_zoom(cls, pdf_path: str, zoom: float) -> None:
        import hashlib
        key = "zoom_" + hashlib.md5(pdf_path.encode()).hexdigest()[:8]
        cls._get().setValue(key, zoom)

    # ------------------------------------------------------------------
    # Last opened document
    # ------------------------------------------------------------------

    @classmethod
    def get_last_opened_doc(cls) -> str | None:
        val = cls._get().value("last_opened_doc", None)
        return val if val else None

    @classmethod
    def set_last_opened_doc(cls, path: str) -> None:
        cls._get().setValue("last_opened_doc", path)

    # ------------------------------------------------------------------
    # Last active view (manager or viewer)
    # ------------------------------------------------------------------

    @classmethod
    def get_last_active_view(cls) -> str:
        """Return 'manager' or 'viewer' depending on what was open last."""
        return str(cls._get().value("last_active_view", "manager"))

    @classmethod
    def set_last_active_view(cls, view: str) -> None:
        cls._get().setValue("last_active_view", view)
