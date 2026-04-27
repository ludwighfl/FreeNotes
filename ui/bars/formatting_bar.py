"""Floating formatting bar for TextBoxItem inline editing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QSize, Signal
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPaintEvent,
    QPen,
    QTextBlockFormat,
    QTextListFormat,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QVBoxLayout,
    QMenu,
    QToolButton,
    QWidget,
)

from app.app_state import AppState
from ui.components.icon_factory import IconFactory
from ui.popups.font_size_widget import FontSizeWidget
from core.i18n import tr

if TYPE_CHECKING:
    from items.text_box_item import TextBoxItem


class FormattingBar(QWidget):
    """Floating formatting bar shown when the text tool is active.

    Hovers above the PDF canvas (child of viewer_window, not page_view)
    and provides controls for font family, size, bold, italic, underline,
    strikethrough, alignment, and lists.
    """

    color_at_cursor = Signal(QColor)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("FormattingBar")
        self.setFixedHeight(42)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # --- Drop shadow ---
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(QPointF(0, 3))
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

        # --- Layout ---
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 1, 8, 7)
        layout.setSpacing(4)

        # --- Font family ---
        self._font_combo = QComboBox()
        self._font_combo.addItems([
            "Arial", "Times New Roman", "Courier New",
            "Georgia", "Helvetica", "Verdana",
        ])
        self._font_combo.setFixedWidth(130)
        self._font_combo.setObjectName("fontCombo")
        self._font_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # --- Font size (custom widget) ---
        self._size_spin = FontSizeWidget()

        # --- Format toggle buttons (with visual style) ---
        self._bold_btn = self._make_format_btn("B", tr("format.bold"), "bold")
        self._italic_btn = self._make_format_btn("I", tr("format.italic"), "italic")
        self._underline_btn = self._make_format_btn(
            "U", tr("format.underline"), "underline")
        self._strike_btn = self._make_format_btn(
            "S", tr("format.strikethrough"), "strikethrough")

        # --- Alignment buttons (Lucide SVG icons) ---
        self._align_left_btn = self._make_icon_btn(
            "align_left", tr("format.align_left"))
        self._align_center_btn = self._make_icon_btn(
            "align_center", tr("format.align_center"))
        self._align_right_btn = self._make_icon_btn(
            "align_right", tr("format.align_right"))

        self._align_group = QButtonGroup(self)
        self._align_group.setExclusive(True)
        self._align_group.addButton(self._align_left_btn)
        self._align_group.addButton(self._align_center_btn)
        self._align_group.addButton(self._align_right_btn)

        # --- Assemble layout ---
        font_container = QWidget()
        font_layout = QVBoxLayout(font_container)
        font_layout.setContentsMargins(0, 1, 0, 0)
        font_layout.setSpacing(0)
        font_layout.addWidget(self._font_combo)
        
        layout.addWidget(font_container)
        layout.addWidget(self._size_spin)
        layout.addWidget(self._make_separator())
        layout.addWidget(self._bold_btn)
        layout.addWidget(self._italic_btn)
        layout.addWidget(self._underline_btn)
        layout.addWidget(self._strike_btn)
        layout.addWidget(self._make_separator())
        layout.addWidget(self._align_left_btn)
        layout.addWidget(self._align_center_btn)
        layout.addWidget(self._align_right_btn)

        # --- Internal state ---
        self._active_box: TextBoxItem | None = None
        self._updating: bool = False  # prevents feedback loops

        # --- Connect signals ---
        self._connect_signals()

        # --- Initially hidden ---
        self.hide()

    # ==================================================================
    # Widget factory helpers
    # ==================================================================

    @staticmethod
    def _make_format_btn(
        text: str, tooltip: str, style: str = "normal"
    ) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setFixedSize(30, 28)
        btn.setObjectName("formatBtn")
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        font = QFont(btn.font())
        font.setPointSize(13)

        if style == "bold":
            font.setBold(True)
        elif style == "italic":
            font.setItalic(True)
        elif style == "underline":
            font.setUnderline(True)
        elif style == "strikethrough":
            font.setStrikeOut(True)

        btn.setFont(font)
        return btn

    @staticmethod
    def _make_icon_btn(icon_name: str, tooltip: str) -> QToolButton:
        """Create a 30×28 icon button using a Lucide SVG from IconFactory."""
        btn = QToolButton()
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setFixedSize(30, 28)
        btn.setObjectName("formatBtn")
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setIcon(IconFactory.create(icon_name, size=16))
        btn.setIconSize(QSize(16, 16))
        return btn

    @staticmethod
    def _make_separator() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("FormatSeparator")
        sep.setFixedHeight(24)
        sep.setFixedWidth(1)
        return sep

    # ==================================================================
    # Signal wiring
    # ==================================================================

    def _connect_signals(self) -> None:
        self._font_combo.currentTextChanged.connect(self._on_font_family_changed)
        self._size_spin.valueChanged.connect(self._on_font_size_changed)
        self._bold_btn.toggled.connect(self._on_bold_toggled)
        self._italic_btn.toggled.connect(self._on_italic_toggled)
        self._underline_btn.toggled.connect(self._on_underline_toggled)
        self._strike_btn.toggled.connect(self._on_strike_toggled)
        self._align_left_btn.toggled.connect(
            lambda checked: self._on_align_changed(
                Qt.AlignmentFlag.AlignLeft, checked))
        self._align_center_btn.toggled.connect(
            lambda checked: self._on_align_changed(
                Qt.AlignmentFlag.AlignHCenter, checked))
        self._align_right_btn.toggled.connect(
            lambda checked: self._on_align_changed(
                Qt.AlignmentFlag.AlignRight, checked))

    # ==================================================================
    # Slots (all guarded by _updating)
    # ==================================================================

    def _on_font_family_changed(self, family: str) -> None:
        if self._updating or not self._active_box:
            return
        self._active_box.apply_font_family(family)

    def _on_font_size_changed(self, size: int) -> None:
        if self._updating or not self._active_box:
            return
        self._active_box.apply_font_size(size)

    def _on_bold_toggled(self, checked: bool) -> None:
        if self._updating or not self._active_box:
            return
        self._active_box.apply_bold(checked)

    def _on_italic_toggled(self, checked: bool) -> None:
        if self._updating or not self._active_box:
            return
        self._active_box.apply_italic(checked)

    def _on_underline_toggled(self, checked: bool) -> None:
        if self._updating or not self._active_box:
            return
        self._active_box.apply_underline(checked)

    def _on_strike_toggled(self, checked: bool) -> None:
        if self._updating or not self._active_box:
            return
        self._active_box.apply_strikethrough(checked)

    def _on_align_changed(
        self, alignment: Qt.AlignmentFlag, checked: bool
    ) -> None:
        if self._updating or not self._active_box or not checked:
            return
        self._active_box.apply_alignment(alignment)



    # ==================================================================
    # Active box property
    # ==================================================================

    @property
    def active_box(self) -> TextBoxItem | None:
        return self._active_box

    @active_box.setter
    def active_box(self, box: TextBoxItem | None) -> None:
        # Disconnect old box
        if self._active_box is not None:
            try:
                self._active_box.cursor_moved.disconnect(self.sync_to_box)
            except RuntimeError:
                pass  # was not connected

        self._active_box = box

        # Connect new box
        if box is not None:
            box.cursor_moved.connect(self.sync_to_box)
            self.sync_to_box()

    # ==================================================================
    # Sync controls to active box's current format
    # ==================================================================

    def sync_to_box(self) -> None:
        """Read format from active TextBoxItem and update all controls."""
        if not self._active_box:
            return

        self._updating = True
        try:
            fmt = self._active_box.get_current_char_format()
            block_fmt = self._active_box.get_current_block_format()
            resolved_font = fmt.font()

            # Font family
            family = resolved_font.family()
            if family:
                idx = self._font_combo.findText(family)
                if idx >= 0:
                    self._font_combo.setCurrentIndex(idx)

            # Font size
            size = resolved_font.pointSize()
            if size > 0:
                self._size_spin.setValue(size)

            # Format buttons
            self._bold_btn.setChecked(resolved_font.bold())
            self._italic_btn.setChecked(resolved_font.italic())
            self._underline_btn.setChecked(resolved_font.underline())
            self._strike_btn.setChecked(resolved_font.strikeOut())

            # Alignment
            align = block_fmt.alignment()
            self._align_left_btn.setChecked(
                bool(align & Qt.AlignmentFlag.AlignLeft)
                or bool(align & Qt.AlignmentFlag.AlignJustify)
            )
            self._align_center_btn.setChecked(
                bool(align & Qt.AlignmentFlag.AlignHCenter)
            )
            self._align_right_btn.setChecked(
                bool(align & Qt.AlignmentFlag.AlignRight)
            )


            # Color at cursor → emit for toolbar sync
            fg = fmt.foreground()
            if fg.style() != Qt.BrushStyle.NoBrush:
                self.color_at_cursor.emit(fg.color())
                current_color = fg.color()
            else:
                self.color_at_cursor.emit(self._active_box.style.color)
                current_color = self._active_box.style.color
            
            # Save the active formats to AppState so new textboxes inherit them.
            # Convert list style into an alignment default if needed, though alignment is separate.
            AppState().update_style(
                font_family=family if family else "Arial",
                font_size=size if size > 0 else 12,
                bold=resolved_font.bold(),
                italic=resolved_font.italic(),
                underline=resolved_font.underline(),
                strikethrough=resolved_font.strikeOut(),
                alignment=align if int(align) != 0 else Qt.AlignmentFlag.AlignLeft,
                color=current_color
            )

        finally:
            self._updating = False

    # ==================================================================
    # Painting
    # ==================================================================

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw rounded-rect background (more reliable than QSS)."""
        from core.app_settings import AppSettings
        is_light = AppSettings.get_theme() == "light"
        bg_color = "#ffffff" if is_light else "#1e1e1e"
        border_color = "#d0d0d0" if is_light else "#3a3a3a"

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor(bg_color)))
        painter.setPen(QPen(QColor(border_color), 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
