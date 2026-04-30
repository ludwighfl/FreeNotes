"""Background worker thread for generating PDF page thumbnails."""

import fitz  # PyMuPDF
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage


class ThumbnailWorker(QThread):
    """Generates PDF page thumbnails in a background thread.

    Opens its own fitz.Document instance to avoid holding the
    DocumentManager._lock during rendering, which would block the
    main thread from accessing page metadata.
    """
    thumbnail_ready = Signal(int, int, QImage)  # generation_id, idx, image

    def __init__(self, doc_manager, indices: list[int], dpi: int, use_hidpi: bool, generation_id: int):
        super().__init__()
        self._doc_path: str = str(doc_manager._path) if doc_manager._path else ""
        self._indices = indices
        self._dpi = dpi
        self._use_hidpi = use_hidpi
        self._generation_id = generation_id
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel the rendering process."""
        self._cancelled = True

    def run(self) -> None:
        """Render thumbnails using an independent fitz.Document."""
        if not self._doc_path:
            return

        try:
            doc = fitz.open(self._doc_path)
        except Exception:
            return

        try:
            for i in self._indices:
                if self._cancelled:
                    break
                if i < 0 or i >= doc.page_count:
                    continue
                try:
                    page = doc.load_page(i)
                    zoom = self._dpi / 72.0
                    matrix = fitz.Matrix(zoom, zoom)
                    pix = page.get_pixmap(matrix=matrix, alpha=False)

                    img = QImage(
                        pix.samples,
                        pix.width,
                        pix.height,
                        pix.stride,
                        QImage.Format.Format_RGB888,
                    )
                    img = img.copy()  # deep-copy so QImage owns the buffer
                except Exception:
                    continue

                if not self._cancelled:
                    self.thumbnail_ready.emit(self._generation_id, i, img)
        finally:
            doc.close()
