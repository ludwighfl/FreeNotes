"""Background worker thread for generating PDF page thumbnails."""

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage


class ThumbnailWorker(QThread):
    """Generates PDF page thumbnails in a background thread using DocumentManager."""
    thumbnail_ready = Signal(int, int, QImage)  # generation_id, idx, image

    def __init__(self, doc_manager, indices: list[int], dpi: int, use_hidpi: bool, generation_id: int):
        super().__init__()
        self._doc_manager = doc_manager
        self._indices = indices
        self._dpi = dpi
        self._use_hidpi = use_hidpi
        self._generation_id = generation_id
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel the rendering process."""
        self._cancelled = True

    def run(self) -> None:
        """Render thumbnails sequentially and emit them."""
        for i in self._indices:
            if self._cancelled:
                break
            img = self._doc_manager.get_page_image(i, self._dpi, use_hidpi=self._use_hidpi)
            if not self._cancelled:
                self.thumbnail_ready.emit(self._generation_id, i, img)
