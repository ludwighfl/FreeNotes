"""Document manager – open, close, and cache PDF page renders."""

from collections import OrderedDict
from pathlib import Path

import fitz  # PyMuPDF
from PySide6.QtGui import QPixmap

from .pdf_renderer import PdfRenderer


class DocumentManager:
    """Manages a single open PDF document with an LRU page-render cache.

    fitz is imported ONLY in this file and in PdfRenderer (same core package).
    """

    CACHE_MAX_SIZE: int = 50

    def __init__(self) -> None:
        self._document: fitz.Document | None = None
        self._path: Path | None = None
        self._renderer: PdfRenderer = PdfRenderer()
        self.page_map: list[int] = []
        # LRU cache: key = (page_index, dpi), value = QPixmap
        self._cache: OrderedDict[tuple[int, int], QPixmap] = OrderedDict()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open_document(self, path: Path) -> bool:
        """Open a PDF document. Closes any previously open document first.

        Args:
            path: Filesystem path to the PDF file.

        Returns:
            True if the document was opened successfully, False otherwise.
        """
        self.close_document()
        try:
            self._document = fitz.open(str(path))
            self._path = path
            self.page_map = list(range(self._document.page_count))
            return True
        except Exception:
            self._document = None
            self._path = None
            return False

    def close_document(self) -> None:
        """Close the currently open document and clear the cache."""
        if self._document is not None:
            self._document.close()
            self._document = None
        self._path = None
        self.page_map = []
        self._cache.clear()

    def get_page_count(self) -> int:
        """Return the number of pages in the open document (0 if none)."""
        if self._document is None:
            return 0
        return self._document.page_count

    def get_page_pixmap(self, page_index: int, dpi: int = 150) -> QPixmap:
        """Return a rendered QPixmap for the given page, using LRU cache.

        Args:
            page_index: Zero-based page index.
            dpi: Render resolution (default 150).

        Returns:
            QPixmap of the rendered page, or a null QPixmap on error.
        """
        if self._document is None:
            return QPixmap()
        if page_index < 0 or page_index >= self._document.page_count:
            return QPixmap()

        cache_key = (page_index, dpi)

        # Check cache – move to end on hit (LRU)
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        # Render and cache
        page = self._document.load_page(page_index)
        pixmap = self._renderer.render_page(page, dpi)

        self._cache[cache_key] = pixmap
        self._cache.move_to_end(cache_key)

        # Evict oldest if over capacity
        while len(self._cache) > self.CACHE_MAX_SIZE:
            self._cache.popitem(last=False)

        return pixmap

    def get_page_size(self, page_index: int) -> tuple[float, float]:
        """Return the (width, height) of a page in points.

        Args:
            page_index: Zero-based page index.

        Returns:
            Tuple of (width, height) in PDF points, or A4 fallback.
        """
        if self._document is None:
            return (595.0, 842.0)
        if page_index < 0 or page_index >= self._document.page_count:
            return (595.0, 842.0)
        page = self._document.load_page(page_index)
        rect = page.rect
        return (rect.width, rect.height)

    def reorder_pages(self, new_order: list[int]) -> None:
        """Reorder pages in the open document."""
        if self._document is None:
            return
        self._document.select(new_order)
        self.page_map = [self.page_map[i] for i in new_order]
        
        # Remap cache keys instead of clearing (performance fix)
        new_cache = OrderedDict()
        for key, pixmap in self._cache.items():
            old_idx, dpi = key
            try:
                new_idx = new_order.index(old_idx)
                new_cache[(new_idx, dpi)] = pixmap
            except ValueError:
                pass
        self._cache = new_cache

    def insert_page(
        self, at_index: int, source_idx: int | None = None
    ) -> None:
        """Insert a page at the given index.

        Args:
            at_index: Position to insert at.
            source_idx: If None, insert a blank A4 page.
                        If int, copy that page.
        """
        if self._document is None:
            return
        if source_idx is None:
            self._document.insert_page(at_index, width=595, height=842)
            self.page_map.insert(at_index, -1)
        else:
            # copy_page inserts after source, so we use fullcopy + move
            self._document.copy_page(source_idx, at_index)
            self.page_map.insert(at_index, self.page_map[source_idx])
            
        new_cache = OrderedDict()
        for key, pixmap in self._cache.items():
            idx, dpi = key
            new_idx = idx + 1 if idx >= at_index else idx
            new_cache[(new_idx, dpi)] = pixmap
        self._cache = new_cache

    def remove_page(self, page_idx: int) -> None:
        """Delete a page from the document."""
        if self._document is None:
            return
        self._document.delete_page(page_idx)
        self.page_map.pop(page_idx)
        
        new_cache = OrderedDict()
        for key, pixmap in self._cache.items():
            idx, dpi = key
            if idx == page_idx:
                continue
            new_idx = idx - 1 if idx > page_idx else idx
            new_cache[(new_idx, dpi)] = pixmap
        self._cache = new_cache

    def save_page_bytes(self, page_idx: int) -> bytes:
        """Save a single page as PDF bytes (for undo)."""
        import fitz
        if self._document is None:
            return b""
        temp = fitz.open()
        temp.insert_pdf(
            self._document, from_page=page_idx, to_page=page_idx)
        data = temp.tobytes()
        temp.close()
        return data

    def restore_page(self, at_index: int, page_bytes: bytes) -> None:
        """Restore a previously saved page from bytes."""
        import fitz
        if self._document is None or not page_bytes:
            return
        temp = fitz.open("pdf", page_bytes)
        self._document.insert_pdf(
            temp, from_page=0, to_page=0, start_at=at_index)
        # We don't track restored page in page_map here since commands handles page_map?
        # Actually, undo/redo of delete_page should restore the page_map value via the command.
        temp.close()
        self._cache.clear()

    def apply_page_map(self, page_map: list[int]) -> None:
        """Create a new document following the page_map and replace the current one."""
        if self._document is None:
            return
        import fitz
        new_doc = fitz.open()
        old_doc = self._document
        for orig_idx in page_map:
            if orig_idx == -1:
                new_doc.insert_page(-1, width=595, height=842)
            else:
                new_doc.insert_pdf(old_doc, from_page=orig_idx, to_page=orig_idx)
                
        self._document.close()
        self._document = new_doc
        self.page_map = list(page_map)
        self._cache.clear()

    @property
    def path(self) -> Path | None:
        """The path of the currently open document."""
        return self._path

    @property
    def is_open(self) -> bool:
        """Whether a document is currently open."""
        return self._document is not None

    def search_text(self, query: str) -> list[dict]:
        """Search for text across all pages.

        Args:
            query: Text to search for.

        Returns:
            List of dicts with keys: page_index, rect (fitz.Rect), text.
        """
        if not self._document or not query.strip():
            return []

        results: list[dict] = []
        for page_idx in range(self._document.page_count):
            page = self._document.load_page(page_idx)
            hits = page.search_for(query, quads=False)
            for rect in hits:
                results.append({
                    "page_index": page_idx,
                    "rect": rect,
                    "text": query,
                })
        return results
