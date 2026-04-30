"""Thread-safe LRU tile cache for PDF page tiles."""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from enum import IntEnum

from PySide6.QtGui import QImage


class MipLevel(IntEnum):
    """Mipmap resolution levels for progressive tile rendering."""
    THUMB  = 0   # ~36 DPI  — shown immediately on open/zoom-out
    MEDIUM = 1   # ~72 DPI  — shown while full-res is rendering
    FULL   = 2   # ~150 DPI — final sharp render


@dataclass(frozen=True)
class TileKey:
    """Immutable key identifying a single tile in the cache."""
    page_index: int
    tile_col:   int        # column index in the tile grid
    tile_row:   int        # row index in the tile grid
    mip_level:  MipLevel


class TileCache:
    """Thread-safe LRU cache for rendered PDF page tiles.

    Uses :class:`collections.OrderedDict` for O(1) LRU eviction and
    :class:`threading.Lock` to allow safe concurrent access from
    QThreadPool workers.

    Capacity is capped at *MAX_TILES* entries (~200 MB at 512×512 RGBA).
    """

    # Increased from 200 to 400 tiles.
    # Memory estimate: 400 × 1280×1280 px × 4 bytes (RGBA) = ~2.5 GB worst case.
    # In practice much less: THUMB tiles are 36/150 × 1280 = ~307 px physical,
    # MEDIUM tiles ~614 px physical.
    MAX_TILES: int = 400

    # Approximate memory per tile in bytes (for logging/diagnostics only)
    _BYTES_PER_TILE_ESTIMATE: int = 1280 * 1280 * 4  # ~6 MB worst case

    def __init__(self) -> None:
        self._cache: OrderedDict[TileKey, QImage] = OrderedDict()
        self._lock = threading.Lock()

    def estimated_memory_mb(self) -> float:
        """Return a rough estimate of current cache memory usage in MB.

        Uses worst-case FULL tile size for all tiles regardless of actual
        mip level — real usage is typically 4–8× lower.
        """
        with self._lock:
            return len(self._cache) * self._BYTES_PER_TILE_ESTIMATE / (1024 * 1024)

    def resize(self, max_tiles: int) -> None:
        """Change the maximum number of cached tiles.

        Evicts oldest entries immediately if the new limit is smaller
        than the current cache size.
        """
        with self._lock:
            self.MAX_TILES = max_tiles
            while len(self._cache) > self.MAX_TILES:
                self._cache.popitem(last=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: TileKey) -> QImage | None:
        """Return the cached image for *key*, promoting it to most-recent.

        Returns ``None`` on a cache miss.
        """
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def put(self, key: TileKey, image: QImage) -> None:
        """Insert or update *key* with *image*, evicting the oldest
        entry when the cache exceeds :pyattr:`MAX_TILES`.
        """
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = image
            while len(self._cache) > self.MAX_TILES:
                self._cache.popitem(last=False)

    def invalidate_page(self, page_index: int) -> None:
        """Remove **all** tiles belonging to *page_index* (every mip
        level and tile position).
        """
        with self._lock:
            keys_to_remove = [
                k for k in self._cache if k.page_index == page_index
            ]
            for k in keys_to_remove:
                del self._cache[k]

    def invalidate_all(self) -> None:
        """Drop every entry in the cache."""
        with self._lock:
            self._cache.clear()

    def contains(self, key: TileKey) -> bool:
        """Return ``True`` if *key* is present in the cache.

        Does **not** promote the entry in LRU order.
        """
        with self._lock:
            return key in self._cache

    def contains_batch(self, keys: list[TileKey]) -> set[TileKey]:
        """Return the subset of *keys* present in the cache.

        Acquires the lock only once for all keys instead of once per key.
        Does **not** promote entries in LRU order.
        """
        with self._lock:
            return {k for k in keys if k in self._cache}

    def remap_after_insert(self, at_index: int) -> None:
        """Shift tile indices up by 1 for pages >= *at_index*.

        Tiles for pages before *at_index* are left untouched.
        """
        with self._lock:
            new_cache: OrderedDict[TileKey, QImage] = OrderedDict()
            for key, img in self._cache.items():
                if key.page_index >= at_index:
                    new_key = TileKey(
                        page_index=key.page_index + 1,
                        tile_col=key.tile_col,
                        tile_row=key.tile_row,
                        mip_level=key.mip_level,
                    )
                    new_cache[new_key] = img
                else:
                    new_cache[key] = img
            self._cache = new_cache

    def remap_after_delete(self, at_index: int) -> None:
        """Remove tiles for *at_index* and shift indices down by 1 for
        pages > *at_index*.
        """
        with self._lock:
            new_cache: OrderedDict[TileKey, QImage] = OrderedDict()
            for key, img in self._cache.items():
                if key.page_index == at_index:
                    continue  # drop deleted page's tiles
                elif key.page_index > at_index:
                    new_key = TileKey(
                        page_index=key.page_index - 1,
                        tile_col=key.tile_col,
                        tile_row=key.tile_row,
                        mip_level=key.mip_level,
                    )
                    new_cache[new_key] = img
                else:
                    new_cache[key] = img
            self._cache = new_cache
