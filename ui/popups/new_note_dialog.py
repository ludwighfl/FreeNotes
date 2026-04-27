"""Dialog for creating a new note from a preset."""

from pathlib import Path

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont, QImage, QPixmap, QColor
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFrame,
    QScrollArea,
    QWidget,
)

import fitz

from ui.components.icon_factory import IconFactory
from utils.path_helpers import get_app_path
from core.i18n import tr


class PresetButton(QFrame):
    """A button-like widget representing a preset PDF."""

    clicked = Signal(Path)

    def __init__(self, pdf_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pdf_path = pdf_path
        self._is_selected = False

        self.setObjectName("presetButton")
        self.setFixedSize(140, 180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Render thumbnail
        self._thumb_label = QLabel()
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setFixedSize(120, 140)
        
        pixmap = self._render_thumbnail()
        if pixmap:
            self._thumb_label.setPixmap(pixmap.scaled(
                self._thumb_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        layout.addWidget(self._thumb_label)

        # Title
        name = self.pdf_path.stem.capitalize()
        self._title_label = QLabel(name)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setFont(QFont("Segoe UI", 12))
        self._title_label.setObjectName("presetTitleLabel")
        layout.addWidget(self._title_label)

        self.setProperty("selected", False)

    def _render_thumbnail(self) -> QPixmap | None:
        try:
            doc = fitz.open(str(self.pdf_path))
            if doc.page_count > 0:
                page = doc.load_page(0)
                pix = page.get_pixmap(dpi=36)
                img = QImage(
                    pix.samples,
                    pix.width,
                    pix.height,
                    pix.stride,
                    QImage.Format.Format_RGB888,
                )
                return QPixmap.fromImage(img)
            doc.close()
        except Exception as e:
            print(f"Failed to render preset thumbnail for {self.pdf_path}: {e}")
        return None

    def set_selected(self, selected: bool) -> None:
        if self._is_selected != selected:
            self._is_selected = selected
            self.setProperty("selected", selected)
            self.style().unpolish(self)
            self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.pdf_path)
        super().mousePressEvent(event)


class NewNoteDialog(QDialog):
    """Dialog to create a new note from a preset PDF."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("dialog.new_note.title"))
        self.setFixedSize(540, 400)
        self.setObjectName("newNoteDialog")

        self._selected_preset: Path | None = None
        self._preset_buttons: list[PresetButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Presets area

        presets_scroll = QScrollArea()
        presets_scroll.setWidgetResizable(True)
        presets_scroll.setFrameShape(QFrame.Shape.NoFrame)
        presets_scroll.setStyleSheet("background: transparent;")
        presets_scroll.setFixedHeight(220)

        presets_container = QWidget()
        presets_container.setStyleSheet("background: transparent;")
        presets_layout = QHBoxLayout(presets_container)
        presets_layout.setContentsMargins(0, 0, 0, 0)
        presets_layout.setSpacing(16)
        presets_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._load_presets(presets_layout)
        
        presets_scroll.setWidget(presets_container)
        layout.addWidget(presets_scroll)

        # Name input
        name_label = QLabel(tr("dialog.new_note.name_label"))
        name_label.setObjectName("newNoteNameLabel")
        layout.addWidget(name_label)

        self._name_input = QLineEdit(tr("dialog.new_note.default_name"))
        self._name_input.setObjectName("newNoteNameInput")
        self._name_input.textChanged.connect(self._validate)
        layout.addWidget(self._name_input)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        self._cancel_btn = QPushButton(tr("dialog.new_note.cancel"))
        self._cancel_btn.setFixedSize(120, 36)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.reject)
        self._cancel_btn.setObjectName("newNoteCancelBtn")
        btn_layout.addWidget(self._cancel_btn)

        self._ok_btn = QPushButton(tr("dialog.new_note.create"))
        self._ok_btn.setFixedSize(120, 36)
        self._ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ok_btn.clicked.connect(self.accept)
        self._ok_btn.setObjectName("newNoteOkBtn")
        btn_layout.addWidget(self._ok_btn)

        layout.addLayout(btn_layout)

        self._validate()

    def _load_presets(self, layout: QHBoxLayout) -> None:
        presets_dir = get_app_path() / "assets" / "presets"
        if not presets_dir.exists():
            return

        for pdf_path in sorted(presets_dir.glob("*.pdf")):
            btn = PresetButton(pdf_path)
            btn.clicked.connect(self._on_preset_clicked)
            layout.addWidget(btn)
            self._preset_buttons.append(btn)

            # Auto-select the first one
            if self._selected_preset is None:
                self._on_preset_clicked(pdf_path)

    def _on_preset_clicked(self, path: Path) -> None:
        self._selected_preset = path
        for btn in self._preset_buttons:
            btn.set_selected(btn.pdf_path == path)
        self._validate()

    def _validate(self) -> None:
        if not hasattr(self, '_name_input') or not hasattr(self, '_ok_btn'):
            return
        has_name = bool(self._name_input.text().strip())
        has_preset = self._selected_preset is not None
        self._ok_btn.setEnabled(has_name and has_preset)

    @property
    def selected_preset(self) -> Path | None:
        return self._selected_preset

    @property
    def note_name(self) -> str:
        return self._name_input.text().strip()
