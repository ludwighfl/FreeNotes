"""Viewer window – complete PDF viewer with toolbar, sidebar, and page view."""

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QRectF, QTimer
from PySide6.QtGui import QFont, QIntValidator, QShortcut, QKeySequence
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
from core import undo_stack
from ui.scene.page_scene import PageScene
from ui.scene.page_view import PageView
from ui.bars.sidebar_widget import SidebarWidget
from ui.bars.toolbar_widget import ToolbarWidget
from ui.components.icon_factory import IconFactory
from tools.hand_tool import HandTool
from tools.pen_tool import PenTool
from tools.highlighter_tool import HighlighterTool
from tools.eraser_tool import EraserTool
from tools.text_tool import TextTool
from tools.selection_tool import SelectionTool
from tools.shape_tool import ShapeTool
from ui.bars.formatting_bar import FormattingBar
from ui.popups.three_dot_menu import ThreeDotMenu
from ui.components.editable_title_label import EditableTitleLabel

from ui.windows.viewer_file_io import ViewerFileIOMixin
from ui.windows.viewer_tool_manager import ViewerToolManagerMixin


class ViewerWindow(ViewerFileIOMixin, ViewerToolManagerMixin, QWidget):
    """Full viewer screen: toolbar at top, sidebar left, PageView right.

    Functionality is split across mixins:
        ViewerFileIOMixin      – Loading, saving, exporting
        ViewerToolManagerMixin – Tool switching, style updates, undo routing
    """

    # Emits the path of the closed PDF (or None)
    back_requested = Signal(object)

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
        self._shape_tool: ShapeTool = ShapeTool()

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
        self._back_btn.clicked.connect(self._on_back_clicked)
        header_layout.addWidget(self._back_btn)

        # Document title
        self._title_label = EditableTitleLabel("Dokument")
        self._title_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._title_label.setStyleSheet("color: #ffffff;")
        self._title_label.rename_requested.connect(self._on_title_rename_requested)
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
        self._three_dot_menu.load_requested.connect(self._on_load)
        self._three_dot_menu.export_requested.connect(self._on_export)
        self._three_dot_menu.export_as_requested.connect(self._on_export_as)
        self._three_dot_menu.clear_annotations_requested.connect(self._on_clear_annotations)
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
        self._app_state.total_pages_changed.connect(self._on_total_pages_changed)
        self._page_input.returnPressed.connect(self._on_page_input_entered)
        self._toolbar.tool_changed.connect(self._on_tool_changed)
        self._toolbar.style_changed.connect(self._on_style_changed)
        self._toolbar.eraser_mode_changed.connect(self._on_eraser_mode_changed)
        self._toolbar.selection_mode_changed.connect(
            self._selection_tool.set_mode)

        # Manually sync the active eraser mode from the toolbar since it emitted before we connected
        from core.app_settings import AppSettings
        self._on_eraser_mode_changed(AppSettings.get_eraser_mode())

        # Connect tool_action_completed for undo stack
        self._pen_tool.tool_action_completed.connect(self._on_action_completed)
        self._highlighter_tool.tool_action_completed.connect(self._on_action_completed)
        self._eraser_tool.tool_action_completed.connect(self._on_action_completed)
        self._text_tool.tool_action_completed.connect(self._on_action_completed)

        # Connect global undo stack events to update file modification state
        undo_stack.get_stack().indexChanged.connect(self._on_stack_changed)
        
        self._app_state.document_renamed.connect(self._update_title)
        
        # Autosave timer
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(1000)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self.save_document)

        # Formatting bar (floating, child of self)
        self._formatting_bar = FormattingBar(parent=self)
        self._formatting_bar.color_at_cursor.connect(
            self._toolbar.select_matching_color)

        # Tool switch requested from page_scene (e.g. clicking TextBox with hand tool)
        self._page_scene.tool_switch_requested.connect(self._on_tool_switch_requested)

        # --- Search ---
        from ui.bars.search_bar import SearchBar
        self._search_bar = SearchBar(parent=self)
        self._search_bar.search_changed.connect(self._on_search)
        self._search_bar.navigate_prev.connect(self._search_prev)
        self._search_bar.navigate_next.connect(self._search_next)
        self._search_bar.closed.connect(self._clear_search)

        from items.search_highlight_item import SearchHighlightItem
        self._search_hits: list[dict] = []
        self._search_items: list[SearchHighlightItem] = []
        self._search_current: int = -1

        # Ctrl+F shortcut
        self._search_shortcut = QShortcut(
            QKeySequence("Ctrl+F"), self)
        self._search_shortcut.activated.connect(self._show_search)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_sidebar_page_clicked(self, page_index: int) -> None:
        self._page_view.scroll_to_page(page_index)

    def _on_visible_page_changed(self, page_index: int) -> None:
        if self._app_state.current_page != page_index:
            self._app_state.current_page = page_index

    def _on_page_changed(self, page_index: int) -> None:
        self._page_input.setText(str(page_index + 1))

    def _on_total_pages_changed(self, total: int) -> None:
        self._total_pages_label.setText(str(total))
        from PySide6.QtGui import QIntValidator
        if total > 0:
            self._page_input.setValidator(QIntValidator(1, total, self))
        self._page_input.setText("1")

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
        if hasattr(self, '_search_bar') and self._search_bar.isVisible():
            self._search_bar._reposition()

    # ------------------------------------------------------------------
    # Page management
    # ------------------------------------------------------------------

    def add_page(self, near_idx: int, position: str) -> None:
        """Insert a blank page before or after near_idx."""
        insert_at = near_idx if position == "before" else near_idx + 1
        from commands.add_page_command import AddPageCommand
        cmd = AddPageCommand(
            insert_at=insert_at,
            source_page_idx=None,
            scene=self._page_scene,
            doc_manager=self._doc_manager,
            sidebar=self._sidebar,
            label="Leere Seite einfügen",
        )
        undo_stack.push(cmd)

    def duplicate_page(self, page_idx: int) -> None:
        """Duplicate a page (including annotations)."""
        from commands.add_page_command import AddPageCommand
        cmd = AddPageCommand(
            insert_at=page_idx + 1,
            source_page_idx=page_idx,
            scene=self._page_scene,
            doc_manager=self._doc_manager,
            sidebar=self._sidebar,
            label="Seite duplizieren",
        )
        undo_stack.push(cmd)

    def delete_page(self, page_idx: int) -> None:
        """Delete a page (undoable)."""
        if self._doc_manager.get_page_count() <= 1:
            return  # Can't delete last page
        from commands.delete_page_command import DeletePageCommand
        cmd = DeletePageCommand(
            page_idx=page_idx,
            scene=self._page_scene,
            doc_manager=self._doc_manager,
            sidebar=self._sidebar,
        )
        undo_stack.push(cmd)

    def clear_ui(self) -> None:
        """Instantly blanks out the viewer UI to hide previous documents during transitions."""
        self._page_scene.clear()
        if hasattr(self._page_scene, '_page_items'):
            self._page_scene._page_items.clear()
            self._page_scene._page_rects.clear()
            self._page_scene._tile_cache._cache.clear()
        self._sidebar.clear()
        self._title_label.setText("Lädt ...")
        self._ext_label.setText("")
        self._breadcrumb_label.setText("")
        if hasattr(self, '_total_pages_label'):
            self._total_pages_label.setText("0")

    def _on_back_clicked(self) -> None:
        """Save zoom and navigate back to manager."""
        self._save_current_zoom()
        self._clear_search()
        
        # Ensure all pending changes are saved before closing
        self.save_document()
        
        closed_path = self._app_state.current_pdf_path
        
        self._page_scene.set_tool(None)
        if hasattr(self._page_scene, '_tile_renderer'):
            self._page_scene._tile_renderer.cancel_all()
            self._page_scene._tile_renderer.wait_for_idle()
        self._page_scene.clear()
        self._doc_manager.close_document()
        self._app_state.current_pdf_path = None
        self._app_state.freenotes_path = None
        
        self.back_requested.emit(closed_path)

    # ------------------------------------------------------------------
    # Full-text search
    # ------------------------------------------------------------------

    def _show_search(self) -> None:
        """Show the search bar (Ctrl+F)."""
        self._search_bar.show_search()

    def _on_search(self, query: str) -> None:
        """Handle search input (debounced)."""
        self._clear_search_items()

        if not query.strip():
            self._search_bar.update_count(0, 0)
            return

        hits = self._doc_manager.search_text(query)
        self._search_hits = hits
        self._search_current = 0 if hits else -1

        self._draw_search_highlights()

        if hits:
            self._scroll_to_hit(0)
        self._search_bar.update_count(
            self._search_current, len(hits))

    def _draw_search_highlights(self) -> None:
        """Create highlight items for all search hits."""
        from items.search_highlight_item import SearchHighlightItem

        for i, hit in enumerate(self._search_hits):
            page_idx = hit["page_index"]
            fitz_rect = hit["rect"]

            scene_rect = self._fitz_rect_to_scene(fitz_rect, page_idx)
            if scene_rect.isEmpty():
                continue

            item = SearchHighlightItem(
                scene_rect,
                is_current=(i == self._search_current))
            self._page_scene.addItem(item)
            self._search_items.append(item)

    def _fitz_rect_to_scene(
        self, fitz_rect: object, page_idx: int
    ) -> QRectF:
        """Convert a fitz.Rect (PDF coords) to scene coordinates."""
        page_rect = self._page_scene.get_page_rect(page_idx)
        if page_rect.isEmpty():
            return QRectF()

        pdf_w, pdf_h = self._doc_manager.get_page_size(page_idx)
        if pdf_w <= 0 or pdf_h <= 0:
            return QRectF()

        sx = page_rect.width() / pdf_w
        sy = page_rect.height() / pdf_h

        return QRectF(
            page_rect.x() + fitz_rect.x0 * sx,
            page_rect.y() + fitz_rect.y0 * sy,
            (fitz_rect.x1 - fitz_rect.x0) * sx,
            (fitz_rect.y1 - fitz_rect.y0) * sy)

    def _scroll_to_hit(self, idx: int) -> None:
        """Scroll to a specific search hit."""
        if idx < 0 or idx >= len(self._search_hits):
            return
        hit = self._search_hits[idx]
        page_idx = hit["page_index"]

        self._page_view.scroll_to_page(page_idx)

        scene_rect = self._fitz_rect_to_scene(hit["rect"], page_idx)
        if not scene_rect.isEmpty():
            self._page_view.ensureVisible(
                scene_rect.x(),
                scene_rect.y(),
                scene_rect.width(),
                scene_rect.height(),
                100, 100)

    def _search_prev(self) -> None:
        """Navigate to previous search hit."""
        if not self._search_hits:
            return
        if self._search_current >= 0 and self._search_current < len(self._search_items):
            self._search_items[self._search_current].set_current(False)
        self._search_current = (
            self._search_current - 1) % len(self._search_hits)
        if self._search_current < len(self._search_items):
            self._search_items[self._search_current].set_current(True)
        self._scroll_to_hit(self._search_current)
        self._search_bar.update_count(
            self._search_current, len(self._search_hits))

    def _search_next(self) -> None:
        """Navigate to next search hit."""
        if not self._search_hits:
            return
        if self._search_current >= 0 and self._search_current < len(self._search_items):
            self._search_items[self._search_current].set_current(False)
        self._search_current = (
            self._search_current + 1) % len(self._search_hits)
        if self._search_current < len(self._search_items):
            self._search_items[self._search_current].set_current(True)
        self._scroll_to_hit(self._search_current)
        self._search_bar.update_count(
            self._search_current, len(self._search_hits))

    def _clear_search_items(self) -> None:
        """Remove all search highlight items from the scene."""
        for item in self._search_items:
            self._page_scene.removeItem(item)
        self._search_items.clear()
        self._search_hits = []
        self._search_current = -1

    def _clear_search(self) -> None:
        """Clear search and hide the bar."""
        self._clear_search_items()
        self._search_bar.update_count(0, 0)

    def keyPressEvent(self, event) -> None:
        """Handle Escape to close search bar."""
        if event.key() == Qt.Key.Key_Escape:
            if hasattr(self, '_search_bar') and self._search_bar.isVisible():
                self._search_bar._on_close()
                return
        super().keyPressEvent(event)

    def _on_title_rename_requested(self, new_name: str) -> None:
        """Called when the user renames the document via the EditableTitleLabel."""
        if not new_name or not self._app_state.freenotes_path:
            return
            
        from commands.rename_document_command import RenameDocumentCommand
        from core.undo_stack import get_stack
        
        old_name = self._title_label.text()
        if old_name == new_name:
            return
            
        cmd = RenameDocumentCommand(self, old_name, new_name)
        get_stack().push(cmd)
