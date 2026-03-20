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
