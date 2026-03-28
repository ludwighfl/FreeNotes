"""Font size widget – compact spin-box with visible ▲/▼ arrow buttons."""

from PySide6.QtCore import Qt, Signal, QEvent, QSize
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QFrame,
)

from ui.icon_factory import IconFactory



class FontSizeWidget(QFrame):
    """Compact font-size control: [12] [▲/▼] — arrows stacked right."""

    valueChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("fontSizeFrame")
        self.setFixedSize(68, 28)
        self._value: int = 12
        self._min_val: int = 6
        self._max_val: int = 144

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Number field (left)
        self._edit = QLineEdit(str(self._value))
        self._edit.setFixedSize(36, 28)
        self._edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit.setObjectName("sizeEdit")
        self._edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._edit.setValidator(
            QIntValidator(self._min_val, self._max_val, self))
        self._edit.installEventFilter(self)

        # Separator line
        self._separator = QFrame()
        self._separator.setObjectName("sizeSeparator")
        self._separator.setFrameShape(QFrame.Shape.VLine)
        self._separator.setFixedWidth(1)
        self._separator.setFixedHeight(28)

        # Arrows (right, stacked vertically)
        arrow_widget = QWidget()
        arrow_widget.setStyleSheet("background: transparent; border: none;")
        arrow_widget.setFixedSize(22, 28)
        arrow_layout = QVBoxLayout(arrow_widget)
        arrow_layout.setContentsMargins(0, 0, 0, 0)
        arrow_layout.setSpacing(0)

        self._up_btn = QToolButton()
        self._up_btn.setIcon(IconFactory.create("chevron_up", size=14))
        self._up_btn.setIconSize(QSize(14, 14))
        self._up_btn.setFixedSize(22, 14)
        self._up_btn.setObjectName("sizeArrowUp")
        self._up_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._up_btn.setAutoRepeat(True)
        self._up_btn.setAutoRepeatDelay(400)
        self._up_btn.setAutoRepeatInterval(80)

        self._down_btn = QToolButton()
        self._down_btn.setIcon(IconFactory.create("chevron_down", size=14))
        self._down_btn.setIconSize(QSize(14, 14))
        self._down_btn.setFixedSize(22, 14)
        self._down_btn.setObjectName("sizeArrowDown")
        self._down_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._down_btn.setAutoRepeat(True)
        self._down_btn.setAutoRepeatDelay(400)
        self._down_btn.setAutoRepeatInterval(80)

        arrow_layout.addWidget(self._up_btn)
        arrow_layout.addWidget(self._down_btn)

        main_layout.addWidget(self._edit)
        main_layout.addWidget(self._separator)
        main_layout.addWidget(arrow_widget)

        self._up_btn.clicked.connect(self._increment)
        self._down_btn.clicked.connect(self._decrement)
        self._edit.editingFinished.connect(self._on_edit_finished)

    def value(self) -> int:
        return self._value

    def setValue(self, v: int) -> None:
        clamped = max(self._min_val, min(self._max_val, v))
        if clamped != self._value:
            self._value = clamped
            self._edit.setText(str(self._value))

    def _increment(self) -> None:
        self.setValue(self._value + 1)
        self.valueChanged.emit(self._value)

    def _decrement(self) -> None:
        self.setValue(self._value - 1)
        self.valueChanged.emit(self._value)

    def _on_edit_finished(self) -> None:
        try:
            v = int(self._edit.text())
            self.setValue(v)
            self.valueChanged.emit(self._value)
        except ValueError:
            self._edit.setText(str(self._value))

    def eventFilter(self, obj, event) -> bool:
        """Watch the QLineEdit for focus events to style the outer frame."""
        if obj == self._edit:
            if event.type() == QEvent.Type.FocusIn:
                self.setProperty("focused", True)
                self.style().unpolish(self)
                self.style().polish(self)
            elif event.type() == QEvent.Type.FocusOut:
                self.setProperty("focused", False)
                self.style().unpolish(self)
                self.style().polish(self)
        return super().eventFilter(obj, event)
