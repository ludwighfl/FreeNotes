"""Editable title label – double-click to rename."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QLineEdit


class EditableTitleLabel(QLabel):
    """A QLabel that turns into a QLineEdit on double click to allow renaming.
    
    Signals:
        rename_requested(str): Emitted when the user finishes editing with a new name.
    """

    rename_requested = Signal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setToolTip("Doppelklick zum Umbenennen")
        
        self._editor = QLineEdit(self)
        self._editor.hide()
        
        # Style matches the label roughly (background transparent, text white)
        self._editor.setStyleSheet(
            "QLineEdit {"
            "  background-color: #2b2d31;"
            "  color: #ffffff;"
            "  border: 1px solid #3B7BF5;"
            "  border-radius: 4px;"
            "  padding: 0 4px;"
            "}"
        )
        
        self._editor.editingFinished.connect(self._on_editing_finished)

    def setFont(self, font):
        """Pass font updates to the editor as well."""
        super().setFont(font)
        self._editor.setFont(font)

    def mouseDoubleClickEvent(self, event):
        """Switch to edit mode on double click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_editing()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)
            
    def start_editing(self):
        """Show the QLineEdit and set focus."""
        self._editor.setText(self.text())
        # Make the editor cover the label entirely, but maybe slightly wider
        rect = self.rect()
        # Ensure minimum width so text doesn't clip
        width = max(rect.width() + 20, 200)
        self._editor.setGeometry(0, -2, width, rect.height() + 4)
        
        self._editor.show()
        self._editor.setFocus()
        self._editor.selectAll()
        
    def _on_editing_finished(self):
        """Called when Enter is pressed or focus is lost."""
        self._editor.hide()
        new_text = self._editor.text().strip()
        if new_text and new_text != self.text():
            self.rename_requested.emit(new_text)
