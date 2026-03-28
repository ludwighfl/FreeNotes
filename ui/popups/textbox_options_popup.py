"""Compact options popup for TextBox – Copy, Cut, Delete."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QByteArray, QEvent, QPointF, QPoint, QSize
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QToolButton,
    QWidget,
)

if TYPE_CHECKING:
    from items.text_box_item import TextBoxItem
    from PySide6.QtWidgets import QGraphicsView


# ---------------------------------------------------------------------------
# Inline Lucide SVG icons
# ---------------------------------------------------------------------------

COPY_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"
 viewBox="0 0 24 24" fill="none" stroke="#cccccc" stroke-width="2"
 stroke-linecap="round" stroke-linejoin="round">
 <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
 <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
</svg>"""

SCISSORS_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"
 viewBox="0 0 24 24" fill="none" stroke="#cccccc" stroke-width="2"
 stroke-linecap="round" stroke-linejoin="round">
 <circle cx="6" cy="6" r="3"/>
 <circle cx="6" cy="18" r="3"/>
 <line x1="20" x2="8.12" y1="4" y2="15.88"/>
 <line x1="14.47" x2="20" y1="14.48" y2="20"/>
 <line x1="8.12" x2="12" y1="8.12" y2="12"/>
</svg>"""

TRASH_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"
 viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"
 stroke-linecap="round" stroke-linejoin="round">
 <path d="M3 6h18"/>
 <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
 <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
 <line x1="10" x2="10" y1="11" y2="17"/>
 <line x1="14" x2="14" y1="11" y2="17"/>
</svg>"""


def _svg_to_icon(svg_str: str) -> QIcon:
    """Render an inline SVG string to a QIcon."""
    renderer = QSvgRenderer(QByteArray(svg_str.encode()))
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


class TextBoxOptionsPopup(QWidget):
    """Horizontal icon-only popup: Copy, Cut | Delete.

    Positioned above (or below) the target TextBoxItem.
    Hides automatically on outside click, tool switch, or action.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("TextBoxOptionsPopup")
        self.setFixedHeight(40)

        # Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(QPointF(0, 2))
        shadow.setColor(QColor(0, 0, 0, 180))
        self.setGraphicsEffect(shadow)

        # Layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        self._copy_btn = self._make_btn(
            _svg_to_icon(COPY_SVG), "Kopieren (Strg+C)",
        )
        self._cut_btn = self._make_btn(
            _svg_to_icon(SCISSORS_SVG), "Ausschneiden (Strg+X)",
        )

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("PopupSeparator")
        sep.setFixedHeight(22)
        sep.setFixedWidth(1)

        self._delete_btn = self._make_btn(
            _svg_to_icon(TRASH_SVG), "Löschen (Entf)",
        )
        self._delete_btn.setObjectName("popupDeleteBtn")

        layout.addWidget(self._copy_btn)
        layout.addWidget(self._cut_btn)
        layout.addWidget(sep)
        layout.addWidget(self._delete_btn)

        # Signals
        self._copy_btn.clicked.connect(self._on_copy)
        self._cut_btn.clicked.connect(self._on_cut)
        self._delete_btn.clicked.connect(self._on_delete)

        # State
        self._target_box: TextBoxItem | None = None
        self._skip_next_press: bool = False  # guard against immediate close

        # Global event filter for outside clicks
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        self.hide()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_btn(icon: QIcon, tooltip: str) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(icon)
        btn.setIconSize(QSize(18, 18))
        btn.setToolTip(tooltip)
        btn.setFixedSize(32, 32)
        btn.setObjectName("popupBtn")
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    # ------------------------------------------------------------------
    # Show / Hide
    # ------------------------------------------------------------------

    def show_for(self, box: TextBoxItem, view: QGraphicsView) -> None:
        """Position and show the popup for *box*."""
        self._target_box = box

        # Box bounding in view coordinates
        box_scene_rect = box.mapRectToScene(box.boundingRect())
        top_view = view.mapFromScene(
            QPointF(box_scene_rect.center().x(), box_scene_rect.top()),
        )
        bot_view = view.mapFromScene(
            QPointF(box_scene_rect.center().x(), box_scene_rect.bottom()),
        )

        # View offset inside parent (viewer_window)
        view_offset = view.mapTo(self.parentWidget(), QPoint(0, 0))

        popup_w = self.sizeHint().width()
        popup_h = 40
        margin = 8

        # Prefer above
        y_above = view_offset.y() + top_view.y() - popup_h - margin
        y_below = view_offset.y() + bot_view.y() + margin

        y = y_above if y_above >= 0 else y_below
        x = view_offset.x() + top_view.x() - popup_w // 2

        # Clamp horizontal
        parent_w = self.parentWidget().width()
        x = max(8, min(x, parent_w - popup_w - 8))

        self.move(int(x), int(y))
        self.setFixedWidth(popup_w)
        self._skip_next_press = True  # skip the triggering click in eventFilter
        self.raise_()
        self.show()

    def hide_popup(self) -> None:
        self._target_box = None
        self.hide()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_copy(self) -> None:
        if self._target_box is None:
            return
        from app.app_state import AppState

        AppState().clipboard_box = self._target_box.clone()
        self.hide_popup()

    def _on_cut(self) -> None:
        if self._target_box is None:
            return
        from app.app_state import AppState
        from commands.cut_textbox_command import CutTextBoxCommand
        from core.undo_stack import get_stack

        AppState().clipboard_box = self._target_box.clone()
        scene = self._target_box.scene()
        if scene is None:
            return
        cmd = CutTextBoxCommand(self._target_box, scene)
        get_stack().push(cmd)
        self.hide_popup()

    def _on_delete(self) -> None:
        if self._target_box is None:
            return
        from commands.remove_textbox_command import RemoveTextBoxCommand
        from core.undo_stack import get_stack

        scene = self._target_box.scene()
        if scene is None:
            return
        cmd = RemoveTextBoxCommand([self._target_box], scene)
        get_stack().push(cmd)
        self.hide_popup()

    # ------------------------------------------------------------------
    # Paint (rounded dark background)
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor("#1e1e1e")))
        painter.setPen(QPen(QColor("#3a3a3a"), 1))
        painter.drawRoundedRect(
            self.rect().adjusted(0, 0, -1, -1), 8, 8,
        )

    # ------------------------------------------------------------------
    # Global event filter (outside click → hide)
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress and self.isVisible():
            # Skip the click that triggered show_for()
            if self._skip_next_press:
                self._skip_next_press = False
                return False
            global_pos = QCursor.pos()
            local_pos = self.mapFromGlobal(global_pos)
            if not self.rect().contains(local_pos):
                self.hide_popup()
        return False
