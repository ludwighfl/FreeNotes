"""Manager view – file browser with folder sidebar and PDF card grid."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QGridLayout,
    QFrame,
    QLabel,
    QPushButton,
    QFileDialog,
    QSizePolicy,
)


class PdfCard(QFrame):
    """Single PDF thumbnail card with preview, filename, and date."""

    double_clicked = Signal(Path)

    def __init__(
        self,
        pdf_path: Path,
        date_str: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pdf_path: Path = pdf_path
        self.setObjectName("pdfCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(200, 260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 10)
        layout.setSpacing(6)

        # Thumbnail placeholder
        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(184, 200)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setObjectName("pdfCardThumb")
        self._thumb_label.setStyleSheet(
            "background: #3a3a3a; border-radius: 4px;"
        )

        # Try rendering first page thumbnail
        self._render_thumbnail()

        layout.addWidget(self._thumb_label)

        # Filename label (bold)
        name = pdf_path.stem
        if len(name) > 22:
            name = name[:20] + "..."
        name_label = QLabel(f"{name}.pdf")
        name_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        name_label.setStyleSheet("color: #ffffff;")
        name_label.setWordWrap(False)
        layout.addWidget(name_label)

        # Date label
        if date_str:
            date_label = QLabel(date_str)
            date_label.setFont(QFont("Segoe UI", 10))
            date_label.setStyleSheet("color: #888888;")
            layout.addWidget(date_label)

    def _render_thumbnail(self) -> None:
        """Render the first page of the PDF as a thumbnail."""
        try:
            import fitz  # noqa: local import for thumbnail only
            doc = fitz.open(str(self._pdf_path))
            if doc.page_count > 0:
                page = doc.load_page(0)
                zoom = 150.0 / 72.0  # Render at 150 DPI for crisp thumbnails
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                from PySide6.QtGui import QImage
                img = QImage(
                    pix.samples, pix.width, pix.height, pix.stride,
                    QImage.Format.Format_RGB888,
                ).copy()
                pixmap = QPixmap.fromImage(img)
                scaled = pixmap.scaled(
                    184, 200,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._thumb_label.setPixmap(scaled)
            doc.close()
        except Exception:
            # Show placeholder on failure
            self._thumb_label.setText("📄")
            self._thumb_label.setStyleSheet(
                "background: #3a3a3a; border-radius: 4px; "
                "color: #888888; font-size: 40px;"
            )

    def mouseDoubleClickEvent(self, event: object) -> None:
        self.double_clicked.emit(self._pdf_path)
        super().mouseDoubleClickEvent(event)


class ManagerView(QWidget):
    """File manager screen with folder sidebar and PDF card grid.

    Left: Folder sidebar (220px fixed width) with dummy entries.
    Right: Scrollable grid of PDF cards (4 columns).
    """

    open_pdf_requested = Signal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("managerView")

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Folder sidebar ---
        sidebar = QWidget()
        sidebar.setObjectName("managerSidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 12)
        sidebar_layout.setSpacing(4)

        title_label = QLabel("Notizen")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #ffffff;")
        sidebar_layout.addWidget(title_label)
        sidebar_layout.addSpacing(12)

        # Folder list
        self._folder_list = QListWidget()
        self._folder_list.setObjectName("folderList")
        dummy_folders = [
            "Alle Dokumente",
            "Fachsprache, wissensch...",
            "Hygiene",
            "Krankengymnastische B...",
            "Massage",
            "Methodische Anwendu...",
            "Physiologie",
            "Prävention und Rehabili...",
            "Prüfung",
            "Sonstiges",
        ]
        for folder in dummy_folders:
            item = QListWidgetItem(f"📁  {folder}")
            item.setSizeHint(QSize(200, 36))
            self._folder_list.addItem(item)
        if self._folder_list.count() > 0:
            self._folder_list.setCurrentRow(0)

        sidebar_layout.addWidget(self._folder_list)
        sidebar_layout.addStretch()
        main_layout.addWidget(sidebar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("managerSeparator")
        main_layout.addWidget(sep)

        # --- Content area ---
        content_widget = QWidget()
        content_widget.setObjectName("managerContent")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 16, 20, 12)
        content_layout.setSpacing(12)

        # Header row
        header = QHBoxLayout()
        folder_title = QLabel("Alle Dokumente")
        folder_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        folder_title.setStyleSheet("color: #ffffff;")
        header.addWidget(folder_title)
        header.addStretch()

        create_btn = QPushButton("+ Erstellen")
        create_btn.setObjectName("createBtn")
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(self._on_create_clicked)
        header.addWidget(create_btn)

        content_layout.addLayout(header)

        # Grid scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setObjectName("managerScroll")

        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(16)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._grid_container)

        content_layout.addWidget(scroll)
        main_layout.addWidget(content_widget, 1)

        self._cards: list[PdfCard] = []

    def add_pdf_card(self, pdf_path: Path, date_str: str = "") -> None:
        """Add a PDF card to the grid.

        Args:
            pdf_path: Path to the PDF file.
            date_str: Optional date string to display.
        """
        card = PdfCard(pdf_path, date_str)
        card.double_clicked.connect(self._on_card_double_clicked)
        row = len(self._cards) // 4
        col = len(self._cards) % 4
        self._grid_layout.addWidget(card, row, col)
        self._cards.append(card)

    def _on_card_double_clicked(self, path: Path) -> None:
        self.open_pdf_requested.emit(path)

    def _on_create_clicked(self) -> None:
        """Open a file dialog to import a PDF."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "PDF importieren",
            "",
            "PDF Dateien (*.pdf);;Alle Dateien (*)",
        )
        if file_path:
            path = Path(file_path)
            self.add_pdf_card(path, "Gerade importiert")
            self.open_pdf_requested.emit(path)

    def scan_directory(self, directory: Path) -> None:
        """Scan a directory for PDF files and add cards.

        Args:
            directory: Directory path to scan.
        """
        if not directory.exists():
            return
        for pdf_file in sorted(directory.glob("*.pdf")):
            self.add_pdf_card(pdf_file)
