"""Background tile rendering pipeline using QThreadPool and QRunnable.

Each tile is rendered by an independent :class:`TileRenderTask` that opens
its own ``fitz.Document`` to avoid cross-thread access to a shared instance.
Rendered pixmaps are inserted into the :class:`TileCache` and a Qt signal
is emitted on the main thread so the scene can update.
"""

from __future__ import annotations

import os
from typing import Callable

import fitz  # PyMuPDF
from PySide6.QtCore import (
    QObject,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from .tile_cache import MipLevel, TileCache, TileKey

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TILE_SIZE_PX: int = 1280  # logical scene pixels (~A4 width at 150 DPI)

# Must match PageScene.RENDER_DPI — the DPI used to convert PDF points
# to scene coordinates.  Tiles at any mip level are scaled so their
# logical size equals TILE_SIZE_PX scene units.
SCENE_DPI: float = 150.0

MIP_DPI: dict[MipLevel, float] = {
    MipLevel.THUMB:  36.0,
    MipLevel.MEDIUM: 72.0,
    MipLevel.FULL:  150.0,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _device_pixel_ratio() -> float:
    """Return the primary screen's device-pixel-ratio (DPR)."""
    app = QApplication.instance()
    if app is not None:
        screen = app.primaryScreen()
        if screen is not None:
            return screen.devicePixelRatio()
    return 1.0


import threading

# ---------------------------------------------------------------------------
# PdfConnectionPool
# ---------------------------------------------------------------------------

class PdfConnectionPool:
    """Thread-safe pool of open fitz.Document instances to avoid I/O blocking."""

    def __init__(self, doc_path: str, capacity: int) -> None:
        self._doc_path = doc_path
        self._capacity = capacity
        self._pool: list[fitz.Document] = []
        self._lock = threading.Lock()
        self._closed = False

    def acquire(self) -> fitz.Document:
        """Get an open document from the pool or open a new one."""
        with self._lock:
            if self._pool:
                return self._pool.pop()
        return fitz.open(self._doc_path)

    def release(self, doc: fitz.Document) -> None:
        """Return the document to the pool or close it if full/closed."""
        with self._lock:
            if not self._closed and len(self._pool) < self._capacity:
                self._pool.append(doc)
            else:
                doc.close()

    def close_all(self) -> None:
        """Close all pooled documents and mark the pool as closed."""
        with self._lock:
            self._closed = True
            for doc in self._pool:
                doc.close()
            self._pool.clear()

# ---------------------------------------------------------------------------
# QRunnable task — one per tile per mip level
# ---------------------------------------------------------------------------

from PySide6.QtCore import QRunnable


class TileRenderTask(QRunnable):
    """Renders a single PDF tile at a given mip level on a worker thread.

    Each task opens its own ``fitz.Document`` so that no fitz object is
    shared across threads.
    """

    def __init__(
        self,
        key: TileKey,
        page_rect: QRectF,
        doc_pool: PdfConnectionPool,
        cache: TileCache,
        callback: Callable[[TileKey], None],
        orig_page_idx: int,
        cached_dpr: float = 1.0,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)

        self._key = key
        self._page_rect = page_rect
        self._doc_pool = doc_pool
        self._cache = cache
        self._callback = callback
        self._orig_page_idx = orig_page_idx
        self._cached_dpr = cached_dpr
        self._is_cancelled = is_cancelled

    # ---- worker entry point -----------------------------------------------

    def run(self) -> None:  # noqa: C901
        """Render the tile and store it in the cache.

        Pipeline:
        1. Check if task was cancelled before starting.
        2. Acquire a fitz.Document from the thread-safe connection pool.
        3. Map the tile rectangle from *scene* coordinates to *PDF points*.
        4. Render only the clipped region via ``fitz.Page.get_pixmap``.
        5. Convert fitz pixmap → ``QImage`` → ``QPixmap``.
        6. Store in cache and invoke the callback on the main thread.
        """
        if self._is_cancelled is not None and self._is_cancelled():
            return

        doc: fitz.Document | None = None
        try:
            scene_w = self._page_rect.width()
            scene_h = self._page_rect.height()
            
            if scene_w <= 0.0 or scene_h <= 0.0:
                return

            if self._orig_page_idx == -1:
                # Inserted blank page - render blank tile
                col = self._key.tile_col
                row = self._key.tile_row
                tile_scene = QRectF(0, row * TILE_SIZE_PX, scene_w, TILE_SIZE_PX)
                tile_scene = tile_scene.intersected(QRectF(0, 0, scene_w, scene_h))
                if tile_scene.isEmpty():
                    return
                # Create white image
                dpi = MIP_DPI[self._key.mip_level]
                dpr = self._cached_dpr
                effective_dpr = dpi * dpr / SCENE_DPI
                # Calculate pixel dimensions exactly like PyMuPDF would
                px_w = int(tile_scene.width() * effective_dpr)
                px_h = int(tile_scene.height() * effective_dpr)
                px_w = max(1, px_w)
                px_h = max(1, px_h)
                img = QImage(px_w, px_h, QImage.Format.Format_RGB888)
                img.fill(Qt.GlobalColor.white)
                img.setDevicePixelRatio(effective_dpr)
                self._cache.put(self._key, img)
                if self._is_cancelled is None or not self._is_cancelled():
                    self._callback(self._key)
                return

            doc = self._doc_pool.acquire()
            if self._orig_page_idx >= doc.page_count:
                return

            page = doc.load_page(self._orig_page_idx)
            page_pdf_rect = page.rect  # fitz.Rect in PDF points

            # Account for page rotation when computing the usable dimensions
            rotation = page.rotation
            if rotation in (90, 270):
                pdf_w = page_pdf_rect.height
                pdf_h = page_pdf_rect.width
            else:
                pdf_w = page_pdf_rect.width
                pdf_h = page_pdf_rect.height

            scene_w = self._page_rect.width()
            scene_h = self._page_rect.height()

            if scene_w <= 0.0 or scene_h <= 0.0:
                return

            # Scale factor: PDF points per scene pixel
            scale_x = pdf_w / scene_w
            scale_y = pdf_h / scene_h

            # Tile rect in scene-local coordinates, clipped to page bounds
            col = self._key.tile_col
            row = self._key.tile_row
            tile_scene = QRectF(
                0, # Span full page width
                row * TILE_SIZE_PX,
                scene_w,
                TILE_SIZE_PX,
            )
            page_local = QRectF(0, 0, scene_w, scene_h)
            tile_scene = tile_scene.intersected(page_local)
            if tile_scene.isEmpty():
                return

            # Final cancellation check right before heavy pixmap rendering
            if self._is_cancelled is not None and self._is_cancelled():
                return

            # Convert to PDF points
            clip = fitz.Rect(
                tile_scene.left()   * scale_x,
                tile_scene.top()    * scale_y,
                tile_scene.right()  * scale_x,
                tile_scene.bottom() * scale_y,
            )

            # DPI / zoom
            dpi = MIP_DPI[self._key.mip_level]
            dpr = self._cached_dpr
            zoom = (dpi * dpr) / 72.0
            matrix = fitz.Matrix(zoom, zoom)

            # --- DisplayList Caching to eliminate repeated parsing overhead ---
            if not hasattr(doc, "_dl_cache"):
                from collections import OrderedDict
                doc._dl_cache = OrderedDict()
                
            dl_cache = doc._dl_cache
            page_idx = self._orig_page_idx
            
            if page_idx not in dl_cache:
                # Compile display list once per thread (annots=False ignores native PDF annotations)
                dl_cache[page_idx] = page.get_displaylist(annots=False)
                # Keep cache small (e.g., 5 pages max per thread) to avoid RAM explosion
                while len(dl_cache) > 5:
                    dl_cache.popitem(last=False)
                    
            dl = dl_cache[page_idx]
            pix = dl.get_pixmap(clip=clip, matrix=matrix, alpha=False)

            # fitz pixmap → QImage
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888,
            )
            img = img.copy()  # deep-copy so QImage owns its buffer

            # Scale factor so the pixmap's logical size matches the tile's
            # scene extent regardless of mip DPI.  At FULL (150 DPI) this
            # equals plain dpr; at lower mips the ratio shrinks so Qt
            # stretches the smaller pixmap to fill the same scene area.
            effective_dpr = dpi * dpr / SCENE_DPI
            img.setDevicePixelRatio(effective_dpr)

            # Store raw QImage in cache (QPixmap conversion MUST happen on main thread)
            self._cache.put(self._key, img)

        except Exception:
            # Rendering failures are silently dropped — the scene will
            # simply not receive a tile_ready signal for this key and can
            # re-request later.
            return
        finally:
            if doc is not None:
                self._doc_pool.release(doc)

        # Invoke callback on the main thread
        if self._is_cancelled is None or not self._is_cancelled():
            self._callback(self._key)


# ---------------------------------------------------------------------------
# TileRenderer — orchestrates the thread pool
# ---------------------------------------------------------------------------


class _SignalRelay(QObject):
    """Internal QObject that relays tile-ready notifications via signal.

    Lives on the main thread.  When a worker thread emits
    :pyattr:`tile_ready`, Qt auto-queues the delivery because the
    receiver (connected slot) lives on a different thread.
    """

    tile_ready = Signal(object)  # carries TileKey


class TileRenderer(QObject):
    """Manages a :class:`QThreadPool` of tile-render workers.

    Attributes:
        tile_ready: Emitted on the **main thread** after a tile has been
            rendered and inserted into the cache.  The payload is the
            :class:`TileKey` of the completed tile.
    """

    tile_ready = Signal(object)  # carries TileKey

    def __init__(self, cache: TileCache) -> None:
        super().__init__()
        self._cache = cache

        # Internal relay so worker callbacks land on the main thread
        self._relay = _SignalRelay()
        self._relay.tile_ready.connect(self.tile_ready)

        # Thread pool — capped to avoid over-saturating the CPU / RAM Bandwidth
        # Bumping default from 4 to 6 gives smoother high-refresh throughput
        from PySide6.QtCore import QThreadPool

        self._pool = QThreadPool()
        max_threads = min(6, os.cpu_count() or 2)
        self._pool.setMaxThreadCount(max_threads)

        # Cache DPR once — avoids per-task QApplication.instance() calls
        self._dpr: float = _device_pixel_ratio()

        # Shared connection pools for PyMuPDF
        self._doc_pools: dict[str, PdfConnectionPool] = {}
        self._pool_lock = threading.Lock()

    def _get_doc_pool(self, doc_path: str) -> PdfConnectionPool:
        with self._pool_lock:
            if doc_path not in self._doc_pools:
                self._doc_pools[doc_path] = PdfConnectionPool(
                    doc_path, capacity=self._pool.maxThreadCount()
                )
            return self._doc_pools[doc_path]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def request_tile(
        self,
        key: TileKey,
        page_rect: QRectF,
        doc_path: str,
        priority: int | None = None,
        orig_page_idx: int = -1,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> None:
        """Enqueue a single tile render task.

        The request is silently ignored if the tile is already present in
        the cache.
        """
        if self._cache.contains(key):
            return

        if priority is None:
            priority = int(key.mip_level)  # THUMB=0 (highest), FULL=2
        task = TileRenderTask(
            key=key,
            page_rect=page_rect,
            doc_pool=self._get_doc_pool(doc_path),
            cache=self._cache,
            callback=self._on_tile_rendered,
            orig_page_idx=orig_page_idx,
            cached_dpr=self._dpr,
            is_cancelled=is_cancelled,
        )
        self._pool.start(task, priority)

    def request_tiles(
        self,
        keys: list[TileKey],
        page_rect: QRectF,
        doc_path: str,
        orig_page_idx: int = -1,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> None:
        """Batch-enqueue multiple tile render tasks.

        Keys already present in the cache are skipped.  Priority is
        determined by mip level (THUMB first, FULL last).
        """
        for key in keys:
            if self._cache.contains(key):
                continue

            priority = int(key.mip_level)
            task = TileRenderTask(
                key=key,
                page_rect=page_rect,
                doc_pool=self._get_doc_pool(doc_path),
                cache=self._cache,
                callback=self._on_tile_rendered,
                orig_page_idx=orig_page_idx,
                cached_dpr=self._dpr,
                is_cancelled=is_cancelled,
            )
            self._pool.start(task, priority)

    def cancel_all(self) -> None:
        """Clear the thread-pool queue and gracefully close Document connections."""
        self._pool.clear()
        with self._pool_lock:
            for pool in self._doc_pools.values():
                pool.close_all()
            self._doc_pools.clear()

    def wait_for_idle(self) -> None:
        """Block until all background tasks finish. Call cancel_all() first!"""
        self._pool.waitForDone()

    def set_priority(self, key: TileKey, priority: int) -> None:
        """Hint the pool to re-prioritise a pending task.

        .. note::
            ``QThreadPool`` does not support changing the priority of an
            already-queued runnable.  This method is provided for API
            completeness; in practice the caller should cancel and
            re-enqueue tasks when priorities change significantly (e.g.
            on viewport scroll).
        """
        # QThreadPool has no reprioritise API — this is intentionally
        # a no-op placeholder.  See docstring above.
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _on_tile_rendered(self, key: TileKey) -> None:
        """Bridge from worker thread → main-thread signal.

        Called directly by :class:`TileRenderTask` from its worker
        thread.  Emitting :pyattr:`_SignalRelay.tile_ready` from a
        non-main thread is safe — Qt auto-queues the delivery because
        the relay QObject lives on the main thread.
        """
        self._relay.tile_ready.emit(key)
