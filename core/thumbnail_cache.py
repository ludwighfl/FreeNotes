from collections import OrderedDict
from pathlib import Path

from PySide6.QtGui import QPixmap


class ThumbnailCache:
    """LRU cache for rendered PDF first-page thumbnails.
    
    Keyed by absolute pdf_path string. Holds QPixmap objects
    already scaled to the target size. Thread-unsafe by design
    (UI-only usage).
    """
    MAX_SIZE: int = 100

    def __init__(self) -> None:
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()

    def get(self, pdf_path: Path, thumb_w: int, thumb_h: int) -> QPixmap | None:
        """Return cached thumbnail or None if not cached."""
        if pdf_path is None:
            return None
        key = str(pdf_path.resolve())
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, pdf_path: Path, pixmap: QPixmap) -> None:
        """Store a thumbnail. Evicts oldest entry if over MAX_SIZE."""
        if pdf_path is None or pixmap is None or pixmap.isNull():
            return
        key = str(pdf_path.resolve())
        self._cache[key] = pixmap
        self._cache.move_to_end(key)
        if len(self._cache) > self.MAX_SIZE:
            self._cache.popitem(last=False)

    def invalidate(self, pdf_path: Path) -> None:
        """Remove a specific entry (e.g. after rename/delete)."""
        if pdf_path is None:
            return
        key = str(pdf_path.resolve())
        self._cache.pop(key, None)
