from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QListWidget,
    QAbstractItemView,
)

from ui.popups.glass_dialog import GlassDialog
from ui.components.icon_factory import IconFactory
from core.app_settings import AppSettings
from app.app_state import AppState
from core.i18n import tr


class MergePdfsDialog(GlassDialog):
    """Dialog to reorder selected PDFs and define a name for the merged PDF."""

    def __init__(self, docs: list[dict], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("dialog.merge.title"))
        self.setFixedSize(500, 420)
        self.setObjectName("mergePdfsDialog")

        # Map document names or dicts to display
        # We store the original documents so we can return them in the new order.
        self._docs = list(docs)
        
        layout = self._content_layout
        layout.setSpacing(12)

        # Instructions
        self._instruction_label = QLabel(tr("dialog.merge.instruction"))
        self._instruction_label.setFont(QFont("Roboto", 10))
        layout.addWidget(self._instruction_label)

        # List and Reorder Buttons Layout
        list_buttons_layout = QHBoxLayout()
        list_buttons_layout.setSpacing(12)

        # List Widget
        self._list_widget = QListWidget()
        self._list_widget.setFont(QFont("Roboto", 10))
        self._list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        
        # Populate List
        for doc in self._docs:
            self._list_widget.addItem(doc.get("name", ""))
            
        list_buttons_layout.addWidget(self._list_widget, 1)

        # Reorder buttons
        reorder_btn_layout = QVBoxLayout()
        reorder_btn_layout.setSpacing(8)
        reorder_btn_layout.addStretch()

        self._up_btn = QPushButton()
        self._up_btn.setFixedSize(36, 36)
        self._up_btn.setIcon(IconFactory.create("chevron_up", color="#cccccc", size=20))
        self._up_btn.setToolTip(tr("dialog.merge.up_tooltip"))
        self._up_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._up_btn.clicked.connect(self._move_up)
        reorder_btn_layout.addWidget(self._up_btn)

        self._down_btn = QPushButton()
        self._down_btn.setFixedSize(36, 36)
        self._down_btn.setIcon(IconFactory.create("chevron_down", color="#cccccc", size=20))
        self._down_btn.setToolTip(tr("dialog.merge.down_tooltip"))
        self._down_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._down_btn.clicked.connect(self._move_down)
        reorder_btn_layout.addWidget(self._down_btn)

        reorder_btn_layout.addStretch()
        list_buttons_layout.addLayout(reorder_btn_layout)

        layout.addLayout(list_buttons_layout)

        # New Name Input Label & Field
        name_layout = QVBoxLayout()
        name_layout.setSpacing(6)
        
        self._name_label = QLabel(tr("dialog.merge.name_label"))
        self._name_label.setFont(QFont("Roboto", 10))
        name_layout.addWidget(self._name_label)

        # Set default name
        default_name = tr("dialog.merge.default_name")
        self._name_input = QLineEdit(default_name)
        self._name_input.setFont(QFont("Roboto", 10))
        self._name_input.returnPressed.connect(self.accept)
        name_layout.addWidget(self._name_input)

        layout.addLayout(name_layout)

        # Dialog control buttons (OK / Cancel)
        ctrl_btn_layout = QHBoxLayout()
        ctrl_btn_layout.setSpacing(8)
        ctrl_btn_layout.addStretch()

        self._cancel_btn = QPushButton(tr("dialog.button.cancel"))
        self._cancel_btn.setFixedHeight(32)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.reject)
        ctrl_btn_layout.addWidget(self._cancel_btn)

        self._ok_btn = QPushButton(tr("dialog.merge.button"))
        self._ok_btn.setFixedHeight(32)
        self._ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ok_btn.clicked.connect(self.accept)
        ctrl_btn_layout.addWidget(self._ok_btn)

        layout.addLayout(ctrl_btn_layout)

        self._update_styles()
        AppState().theme_updated.connect(self._update_styles)

        # Auto-focus input
        self._name_input.setFocus()
        self._name_input.selectAll()

    def _move_up(self) -> None:
        curr_row = self._list_widget.currentRow()
        if curr_row > 0:
            item = self._list_widget.takeItem(curr_row)
            self._list_widget.insertItem(curr_row - 1, item)
            self._list_widget.setCurrentRow(curr_row - 1)

    def _move_down(self) -> None:
        curr_row = self._list_widget.currentRow()
        if curr_row >= 0 and curr_row < self._list_widget.count() - 1:
            item = self._list_widget.takeItem(curr_row)
            self._list_widget.insertItem(curr_row + 1, item)
            self._list_widget.setCurrentRow(curr_row + 1)

    def _update_styles(self) -> None:
        super()._update_styles()
        if not hasattr(self, "_instruction_label"):
            return

        is_light = AppSettings.get_theme() == "light"
        text_color = "#333333" if is_light else "#cccccc"
        input_bg = "#ffffff" if is_light else "#2a2a2a"
        input_border = "#cccccc" if is_light else "#444"
        input_color = "#000000" if is_light else "#ffffff"

        self._instruction_label.setStyleSheet(f"color: {text_color}; background: transparent;")
        self._name_label.setStyleSheet(f"color: {text_color}; background: transparent;")

        self._list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {input_bg};
                border: 1px solid {input_border};
                border-radius: 6px;
                padding: 4px;
                color: {input_color};
            }}
            QListWidget::item {{
                padding: 6px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: #3B7BF5;
                color: #ffffff;
            }}
        """)

        self._name_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {input_bg};
                border: 1px solid {input_border};
                border-radius: 6px;
                padding: 6px 10px;
                color: {input_color};
            }}
            QLineEdit:focus {{
                border-color: #3B7BF5;
            }}
        """)

        # Reorder buttons
        for btn, icon in [(self._up_btn, "chevron_up"), (self._down_btn, "chevron_down")]:
            btn.setIcon(IconFactory.create(icon, color="#3B7BF5" if is_light else "#cccccc", size=20))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {input_bg};
                    border: 1px solid {input_border};
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: {"#e5e5e5" if is_light else "#353535"};
                }}
            """)

        # OK Button (primary)
        self._ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #3B7BF5;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5090FF;
            }
        """)

        # Cancel Button (secondary)
        cancel_bg = "#e0e0e0" if is_light else "#2d2d2d"
        cancel_hover_bg = "#d5d5d5" if is_light else "#3a3a3a"
        cancel_border = "#cccccc" if is_light else "#444444"
        self._cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {cancel_bg};
                color: {text_color};
                border: 1px solid {cancel_border};
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {cancel_hover_bg};
            }}
        """)

    def get_result(self) -> tuple[list[dict], str]:
        """Returns the sorted list of documents and the new name."""
        # Find order based on current list contents
        sorted_docs = []
        for i in range(self._list_widget.count()):
            name = self._list_widget.item(i).text()
            # Find the corresponding doc
            for doc in self._docs:
                if doc.get("name") == name:
                    sorted_docs.append(doc)
                    break
        return sorted_docs, self._name_input.text().strip()
