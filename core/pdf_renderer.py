"""PDF page renderer – converts fitz.Page objects to QPixmap."""

import fitz  # PyMuPDF
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication


class PdfRenderer:
    """Converts a PyMuPDF page to a Qt QPixmap at a given DPI.

    This is the single point of fitz→Qt image conversion. The pipeline is:
    fitz.Matrix → fitz.Pixmap → bytes → QImage → QPixmap

    Supports HiDPI rendering by detecting the screen's device pixel ratio
    and rendering at the appropriate physical resolution.
    """

    @staticmethod
    def get_device_pixel_ratio() -> float:
        """Return the primary screen's device pixel ratio (e.g. 1.0, 1.5, 2.0)."""
        app = QApplication.instance()
        if app is not None:
            screen = app.primaryScreen()
            if screen is not None:
                return screen.devicePixelRatio()
        return 1.0

    @staticmethod
    def render_page(
        page: fitz.Page,
        dpi: int = 150,
        use_hidpi: bool = True,
    ) -> QImage:
        """Render a fitz.Page to QImage at the specified DPI.

        When use_hidpi is True, the actual rendering DPI is multiplied by
        the device pixel ratio so the pixmap stays crisp on scaled displays.
        The returned QPixmap has its devicePixelRatio set accordingly, so
        Qt lays it out at the logical (requested) size but with extra detail.

        Args:
            page: A PyMuPDF page object.
            dpi: Logical resolution in dots per inch (default 150).
            use_hidpi: Whether to account for screen scaling (default True).

        Returns:
            A QImage of the rendered page.
        """
        dpr = PdfRenderer.get_device_pixel_ratio() if use_hidpi else 1.0
        
        # Increase rendering resolution by 2x for sharper text, but increase
        # devicePixelRatio by 2x as well so the item's logical scene coordinate
        # size stays exactly the same (preserving tool sizes).
        render_scale = min(2.0, dpr)
        
        physical_dpi = dpi * dpr * render_scale

        zoom = physical_dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        # Convert fitz pixmap (RGB) → QImage → QPixmap
        img = QImage(
            pix.samples,
            pix.width,
            pix.height,
            pix.stride,
            QImage.Format.Format_RGB888,
        )
        # Deep copy so QImage owns its data
        img = img.copy()
        
        effective_dpr = dpr * render_scale
        img.setDevicePixelRatio(effective_dpr)
        return img
