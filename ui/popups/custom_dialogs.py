from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QDialog,
)

from ui.popups.glass_dialog import GlassDialog
from ui.components.icon_factory import IconFactory
from core.i18n import tr
from core.app_settings import AppSettings
from app.app_state import AppState

# Register icons specifically for dialogs if they don't exist
try:
    IconFactory.register(
        "help_circle",
        '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>'
    )
    IconFactory.register(
        "alert_triangle",
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'
    )
    IconFactory.register(
        "x_circle",
        '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>'
    )
except Exception:
    pass


class CustomMessageBox(GlassDialog):
    """Frosted ice replacement for QMessageBox."""
    StandardButton = QMessageBox.StandardButton

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "",
        text: str = "",
        icon_name: str = "info",
        icon_color: str = "#3B7BF5",
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self.setMaximumWidth(500)

        self._selected_button: QMessageBox.StandardButton = QMessageBox.StandardButton.NoButton

        # Main message layout
        msg_layout = QHBoxLayout()
        msg_layout.setSpacing(16)

        # Message type icon
        self._msg_icon = QLabel()
        self._msg_icon.setPixmap(
            IconFactory.create_pixmap(icon_name, color=icon_color, size=32)
        )
        self._msg_icon.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        msg_layout.addWidget(self._msg_icon)

        # Message Text
        self._text_label = QLabel(text)
        self._text_label.setFont(QFont("Roboto", 10))
        self._text_label.setWordWrap(True)
        self._text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg_layout.addWidget(self._text_label, 1)

        self._content_layout.addLayout(msg_layout)

        # Button Row
        self._btn_layout = QHBoxLayout()
        self._btn_layout.setSpacing(8)
        self._btn_layout.addStretch()

        self._buttons_to_widgets: dict[QMessageBox.StandardButton, QPushButton] = {}

        # Add buttons in logical order
        btn_list = []
        if buttons & QMessageBox.StandardButton.Yes:
            btn_list.append((QMessageBox.StandardButton.Yes, tr("dialog.button.yes", "Yes"), True))
        if buttons & QMessageBox.StandardButton.Ok:
            btn_list.append((QMessageBox.StandardButton.Ok, tr("dialog.button.ok", "OK"), True))
        if buttons & QMessageBox.StandardButton.No:
            btn_list.append((QMessageBox.StandardButton.No, tr("dialog.button.no", "No"), False))
        if buttons & QMessageBox.StandardButton.Cancel:
            btn_list.append((QMessageBox.StandardButton.Cancel, tr("dialog.button.cancel", "Cancel"), False))

        for btn_type, btn_label, is_primary in btn_list:
            btn = QPushButton(btn_label)
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, bt=btn_type: self._on_button_clicked(bt))
            
            # Apply class property for QSS styling if needed
            btn.setProperty("primary", is_primary)
            self._btn_layout.addWidget(btn)
            self._buttons_to_widgets[btn_type] = btn

        self._content_layout.addLayout(self._btn_layout)
        self._update_button_styles()
        AppState().theme_updated.connect(self._update_button_styles)

    def _on_button_clicked(self, button: QMessageBox.StandardButton) -> None:
        self._selected_button = button
        if button in (QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Ok):
            self.accept()
        else:
            self.reject()

    def _update_button_styles(self) -> None:
        is_light = AppSettings.get_theme() == "light"
        text_color = "#333333" if is_light else "#cccccc"
        
        # Style general controls
        self._text_label.setStyleSheet(f"color: {text_color}; background: transparent;")

        # Custom stylesheet for primary/secondary buttons
        for btn_type, btn in self._buttons_to_widgets.items():
            is_primary = btn.property("primary")
            if is_primary:
                btn.setStyleSheet("""
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
                    QPushButton:pressed {
                        background-color: #2e6be0;
                    }
                """)
            else:
                bg = "#e0e0e0" if is_light else "#2d2d2d"
                hover_bg = "#d5d5d5" if is_light else "#3a3a3a"
                border = "#cccccc" if is_light else "#444444"
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {bg};
                        color: {text_color};
                        border: 1px solid {border};
                        border-radius: 6px;
                        padding: 6px 16px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: {hover_bg};
                    }}
                    QPushButton:pressed {{
                        background-color: {border};
                    }}
                """)

    @classmethod
    def question(
        cls,
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        defaultButton: QMessageBox.StandardButton = QMessageBox.StandardButton.No,
    ) -> QMessageBox.StandardButton:
        dlg = cls(parent, title, text, "help_circle", "#3B7BF5", buttons)
        dlg.exec()
        return dlg._selected_button

    @classmethod
    def information(
        cls,
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    ) -> QMessageBox.StandardButton:
        dlg = cls(parent, title, text, "info", "#3B7BF5", buttons)
        dlg.exec()
        return dlg._selected_button

    @classmethod
    def warning(
        cls,
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        defaultButton: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    ) -> QMessageBox.StandardButton:
        dlg = cls(parent, title, text, "alert_triangle", "#FF9F1C", buttons)
        dlg.exec()
        return dlg._selected_button

    @classmethod
    def critical(
        cls,
        parent: QWidget | None,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    ) -> QMessageBox.StandardButton:
        dlg = cls(parent, title, text, "x_circle", "#F2545B", buttons)
        dlg.exec()
        return dlg._selected_button


class CustomInputDialog(GlassDialog):
    """Frosted ice replacement for QInputDialog."""
    StandardButton = QMessageBox.StandardButton

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "",
        label_text: str = "",
        text: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(400, 180)

        # Label
        self._label = QLabel(label_text)
        self._label.setFont(QFont("Roboto", 10))
        self._content_layout.addWidget(self._label)

        # Input box
        self._input = QLineEdit(text)
        self._input.setFont(QFont("Roboto", 10))
        self._input.returnPressed.connect(self.accept)
        self._content_layout.addWidget(self._input)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        self._cancel_btn = QPushButton(tr("dialog.button.cancel", "Cancel"))
        self._cancel_btn.setFixedHeight(32)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)

        self._ok_btn = QPushButton(tr("dialog.button.ok", "OK"))
        self._ok_btn.setFixedHeight(32)
        self._ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self._ok_btn)

        self._content_layout.addLayout(btn_layout)

        self._update_styles()
        AppState().theme_updated.connect(self._update_styles)

        # Auto-focus input
        self._input.setFocus()
        self._input.selectAll()

    def _update_styles(self) -> None:
        super()._update_styles()
        if not hasattr(self, "_label") or not hasattr(self, "_input"):
            return
            
        is_light = AppSettings.get_theme() == "light"
        text_color = "#333333" if is_light else "#cccccc"
        input_bg = "#ffffff" if is_light else "#2a2a2a"
        input_border = "#cccccc" if is_light else "#444"
        input_color = "#000000" if is_light else "#ffffff"

        self._label.setStyleSheet(f"color: {text_color}; background: transparent;")
        
        self._input.setStyleSheet(f"""
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

    @classmethod
    def getText(
        cls,
        parent: QWidget | None,
        title: str,
        label: str,
        echo: QLineEdit.EchoMode = QLineEdit.EchoMode.Normal,
        text: str = "",
    ) -> tuple[str, bool]:
        dlg = cls(parent, title, label, text)
        # Apply echo mode
        dlg._input.setEchoMode(echo)
        res = dlg.exec()
        return dlg._input.text(), (res == QDialog.DialogCode.Accepted)
