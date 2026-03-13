"""Viewer window – complete PDF viewer with toolbar, sidebar, and page view."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIntValidator
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QFrame,
    QSizePolicy,
)

from app.app_state import AppState
from core.document_manager import DocumentManager
from ui.page_scene import PageScene
from ui.page_view import PageView
from ui.sidebar_widget import SidebarWidget
from ui.toolbar_widget import ToolbarWidget
from ui.icon_factory import IconFactory
from tools.hand_tool import HandTool
from tools.pen_tool import PenTool
from tools.highlighter_tool import HighlighterTool
from tools.eraser_tool import EraserTool
from tools.text_tool import TextTool
from tools.selection_tool import SelectionTool
from ui.formatting_bar import FormattingBar
from ui.three_dot_menu import ThreeDotMenu

from ui.viewer_file_io import ViewerFileIOMixin
from ui.viewer_tool_manager import ViewerToolManagerMixin


class ViewerWindow(ViewerFileIOMixin, ViewerToolManagerMixin, QWidget):
    """Full viewer screen: toolbar at top, sidebar left, PageView right.

    Functionality is split across mixins:
        ViewerFileIOMixin      – Loading, saving, exporting
        ViewerToolManagerMixin – Tool switching, style updates, undo routing
    """

    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("viewerWindow")
        self._app_state: AppState = AppState()
        self._doc_manager: DocumentManager = DocumentManager()

        # Tool instances (reused)
        self._hand_tool: HandTool = HandTool()
        self._pen_tool: PenTool = PenTool()
        self._highlighter_tool: HighlighterTool = HighlighterTool()
        self._eraser_tool: EraserTool = EraserTool()
        self._text_tool: TextTool = TextTool()
        self._selection_tool: SelectionTool = SelectionTool()

        # --- Main vertical layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === TOP BAR (header + toolbar) ===
        top_bar = QWidget()
        top_bar.setObjectName("viewerTopBar")
        top_layout = QVBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        # -- Header row --
        header = QWidget()
        header.setObjectName("viewerHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 4)
        header_layout.setSpacing(8)

        # Back button (Lucide chevron_left)
        self._back_btn = QPushButton()
        self._back_btn.setIcon(
            IconFactory.create("chevron_left", color="#cccccc", size=20)
        )
        self._back_btn.setObjectName("backBtn")
        self._back_btn.setFixedSize(32, 32)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(self._back_btn)

        # Document title
        self._title_label = QLabel("Dokument")
        self._title_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._title_label.setStyleSheet("color: #ffffff;")
        header_layout.addWidget(self._title_label)

        # Extension label
        self._ext_label = QLabel(".pdf")
        self._ext_label.setFont(QFont("Segoe UI", 14))
        self._ext_label.setStyleSheet("color: #888888;")
        header_layout.addWidget(self._ext_label)

        # Breadcrumb
        self._breadcrumb_label = QLabel("")
        self._breadcrumb_label.setFont(QFont("Segoe UI", 11))
        self._breadcrumb_label.setStyleSheet("color: #666666;")
        header_layout.addWidget(self._breadcrumb_label)

        header_layout.addStretch()

        # Three-dot menu (rightmost in header)
        self._three_dot_menu = ThreeDotMenu(self)
        self._three_dot_menu.set_save_enabled(False)
        self._three_dot_menu.load_requested.connect(self._on_load)
        self._three_dot_menu.save_requested.connect(self._on_save)
        self._three_dot_menu.save_as_requested.connect(self._on_save_as)
        self._three_dot_menu.export_requested.connect(self._on_export)
        self._three_dot_menu.export_as_requested.connect(self._on_export_as)
        header_layout.addWidget(self._three_dot_menu)

        top_layout.addWidget(header)

        # -- Toolbar --
        self._toolbar = ToolbarWidget()
        top_layout.addWidget(self._toolbar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("viewerSeparator")
        top_layout.addWidget(sep)

        main_layout.addWidget(top_bar)

        # === CONTENT AREA ===
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # --- Sidebar column ---
        sidebar_column = QWidget()
        sidebar_column.setObjectName("sidebarColumn")
        sidebar_column.setFixedWidth(210)
        sidebar_col_layout = QVBoxLayout(sidebar_column)
        sidebar_col_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_col_layout.setSpacing(0)

        # Page counter
        page_counter_widget = QWidget()
        page_counter_widget.setObjectName("pageCounterBar")
        page_counter_layout = QHBoxLayout(page_counter_widget)
        page_counter_layout.setContentsMargins(12, 8, 12, 8)
        page_counter_layout.setSpacing(4)

        self._page_input = QLineEdit("1")
        self._page_input.setObjectName("pageInput")
        self._page_input.setFixedWidth(40)
        self._page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_input.setFont(QFont("Segoe UI", 12))
        page_counter_layout.addWidget(self._page_input)

        slash_label = QLabel("/")
        slash_label.setFont(QFont("Segoe UI", 12))
        slash_label.setStyleSheet("color: #888888;")
        page_counter_layout.addWidget(slash_label)

        self._total_pages_label = QLabel("0")
        self._total_pages_label.setFont(QFont("Segoe UI", 12))
        self._total_pages_label.setStyleSheet("color: #888888;")
        page_counter_layout.addWidget(self._total_pages_label)

        page_counter_layout.addStretch()
        sidebar_col_layout.addWidget(page_counter_widget)

        # Thumbnails
        self._sidebar = SidebarWidget()
        sidebar_col_layout.addWidget(self._sidebar, 1)

        content_layout.addWidget(sidebar_column)

        # Sidebar separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setObjectName("viewerSidebarSep")
        content_layout.addWidget(sep2)

        # Page scene + view
        self._page_scene = PageScene()
        self._page_view = PageView(self._page_scene)
        self._page_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        content_layout.addWidget(self._page_view, 1)

        main_layout.addWidget(content, 1)

        # --- Connections ---
        self._sidebar.page_clicked.connect(self._on_sidebar_page_clicked)
        self._page_view.visible_page_changed.connect(self._on_visible_page_changed)
        self._app_state.page_changed.connect(self._on_page_changed)
        self._page_input.returnPressed.connect(self._on_page_input_entered)
        self._toolbar.tool_changed.connect(self._on_tool_changed)
        self._toolbar.style_changed.connect(self._on_style_changed)
        self._toolbar.eraser_mode_changed.connect(self._on_eraser_mode_changed)
        self._toolbar.selection_mode_changed.connect(
            self._selection_tool.set_mode)

        # Connect tool_action_completed for undo stack
        self._pen_tool.tool_action_completed.connect(self._on_action_completed)
        self._highlighter_tool.tool_action_completed.connect(self._on_action_completed)
        self._eraser_tool.tool_action_completed.connect(self._on_action_completed)
        self._text_tool.tool_action_completed.connect(self._on_action_completed)

        # Formatting bar (floating, child of self)
        self._formatting_bar = FormattingBar(parent=self)
        self._formatting_bar.color_at_cursor.connect(
            self._toolbar.select_matching_color)

        # Tool switch requested from page_scene (e.g. clicking TextBox with hand tool)
        self._page_scene.tool_switch_requested.connect(self._on_tool_switch_requested)

        # Keyboard shortcuts are handled in PageScene.keyPressEvent to prevent interception
        # of key events when Editing TextBoxes.

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_sidebar_page_clicked(self, page_index: int) -> None:
        self._page_view.scroll_to_page(page_index)

    def _on_visible_page_changed(self, page_index: int) -> None:
        self._page_input.setText(str(page_index + 1))

    def _on_page_changed(self, page_index: int) -> None:
        self._page_input.setText(str(page_index + 1))

    def _on_page_input_entered(self) -> None:
        text = self._page_input.text().strip()
        if text.isdigit():
            page = int(text) - 1
            if 0 <= page < self._app_state.total_pages:
                self._page_view.scroll_to_page(page)

    # ------------------------------------------------------------------
    # FormattingBar positioning
    # ------------------------------------------------------------------

    def _reposition_formatting_bar(self) -> None:
        """Place the formatting bar below the toolbar, horizontally centered."""
        if not hasattr(self, '_formatting_bar'):
            return
        if not hasattr(self, '_toolbar'):
            return

        toolbar_rect = self._toolbar.geometry()
        bar_width = self._formatting_bar.sizeHint().width()
        bar_width = max(bar_width, 400)

        center_x = (self.width() - bar_width) // 2
        y_pos = toolbar_rect.bottom() + 6

        self._formatting_bar.setFixedWidth(bar_width)
        self._formatting_bar.move(center_x, y_pos)
        self._formatting_bar.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition_formatting_bar()
