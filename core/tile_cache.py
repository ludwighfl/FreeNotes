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

    Maintains separate caches for THUMB and FULL/MEDIUM tiles to
    prevent high-res tiles from evicting low-res structural tiles.
    """

    # Limit for high-resolution tiles (FULL, MEDIUM)
    # Memory estimate: 150 × 1280×1280 px × 4 bytes (RGBA) = ~980 MB worst case.
    MAX_FULL_TILES: int = 150
    
    # Limit for thumbnail tiles (THUMB)
    # Keeps practically the whole document readable in RAM without heavy memory cost.
    MAX_THUMB_TILES: int = 1000

    # Approximate memory per tile in bytes (for logging/diagnostics only)
    _BYTES_PER_FULL_ESTIMATE: int = 1280 * 1280 * 4  # ~6 MB
    _BYTES_PER_THUMB_ESTIMATE: int = 300 * 300 * 4   # ~360 KB

    def __init__(self) -> None:
        self._full_cache: OrderedDict[TileKey, QImage] = OrderedDict()
        self._thumb_cache: OrderedDict[TileKey, QImage] = OrderedDict()
        self._lock = threading.Lock()

    def estimated_memory_mb(self) -> float:
        """Return a rough estimate of current cache memory usage in MB.

        Uses worst-case FULL tile size for all full tiles regardless of actual
        mip level — real usage is typically lower.
        """
        with self._lock:
            full_mb = len(self._full_cache) * self._BYTES_PER_FULL_ESTIMATE / (1024 * 1024)
            thumb_mb = len(self._thumb_cache) * self._BYTES_PER_THUMB_ESTIMATE / (1024 * 1024)
            return full_mb + thumb_mb

    def resize(self, max_tiles: int) -> None:
        """Change the maximum number of cached FULL tiles.

        Evicts oldest entries immediately if the new limit is smaller
        than the current cache size. (THUMB limit remains unchanged).
        """
        with self._lock:
            self.MAX_FULL_TILES = max_tiles
            while len(self._full_cache) > self.MAX_FULL_TILES:
                self._full_cache.popitem(last=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: TileKey) -> QImage | None:
        """Return the cached image for *key*, promoting it to most-recent.

        Returns ``None`` on a cache miss.
        """
        with self._lock:
            cache = self._thumb_cache if key.mip_level == MipLevel.THUMB else self._full_cache
            if key not in cache:
                return None
            cache.move_to_end(key)
            return cache[key]

    def put(self, key: TileKey, image: QImage) -> None:
        """Insert or update *key* with *image*, evicting the oldest
        entry when the cache exceeds its specific limit.
        """
        with self._lock:
            cache = self._thumb_cache if key.mip_level == MipLevel.THUMB else self._full_cache
            limit = self.MAX_THUMB_TILES if key.mip_level == MipLevel.THUMB else self.MAX_FULL_TILES
            
            if key in cache:
                cache.move_to_end(key)
            cache[key] = image
            while len(cache) > limit:
                cache.popitem(last=False)

    def invalidate_page(self, page_index: int) -> None:
        """Remove **all** tiles belonging to *page_index* (every mip
        level and tile position).
        """
        with self._lock:
            for cache in (self._full_cache, self._thumb_cache):
                keys_to_remove = [
                    k for k in cache if k.page_index == page_index
                ]
                for k in keys_to_remove:
                    del cache[k]

    def invalidate_all(self) -> None:
        """Drop every entry in the cache."""
        with self._lock:
            self._full_cache.clear()
            self._thumb_cache.clear()

    def contains(self, key: TileKey) -> bool:
        """Return ``True`` if *key* is present in the cache.

        Does **not** promote the entry in LRU order.
        """
        with self._lock:
            cache = self._thumb_cache if key.mip_level == MipLevel.THUMB else self._full_cache
            return key in cache

    def contains_batch(self, keys: list[TileKey]) -> set[TileKey]:
        """Return the subset of *keys* present in the cache.

        Acquires the lock only once for all keys instead of once per key.
        Does **not** promote entries in LRU order.
        """
        with self._lock:
            found = set()
            for k in keys:
                cache = self._thumb_cache if k.mip_level == MipLevel.THUMB else self._full_cache
                if k in cache:
                    found.add(k)
            return found

    def remap_after_insert(self, at_index: int) -> None:
        """Shift tile indices up by 1 for pages >= *at_index*.

        Tiles for pages before *at_index* are left untouched.
        """
        with self._lock:
            self._full_cache = self._do_remap_insert(self._full_cache, at_index)
            self._thumb_cache = self._do_remap_insert(self._thumb_cache, at_index)

    def _do_remap_insert(self, cache: OrderedDict[TileKey, QImage], at_index: int) -> OrderedDict[TileKey, QImage]:
        new_cache: OrderedDict[TileKey, QImage] = OrderedDict()
        for key, img in cache.items():
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
        return new_cache

    def remap_after_delete(self, at_index: int) -> None:
        """Remove tiles for *at_index* and shift indices down by 1 for
        pages > *at_index*.
        """
        with self._lock:
            self._full_cache = self._do_remap_delete(self._full_cache, at_index)
            self._thumb_cache = self._do_remap_delete(self._thumb_cache, at_index)

    def _do_remap_delete(self, cache: OrderedDict[TileKey, QImage], at_index: int) -> OrderedDict[TileKey, QImage]:
        new_cache: OrderedDict[TileKey, QImage] = OrderedDict()
        for key, img in cache.items():
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
        return new_cache
