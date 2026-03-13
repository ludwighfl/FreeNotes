"""Undo stack – module-level singleton wrapper around QUndoStack."""

from PySide6.QtGui import QUndoCommand, QUndoStack

_stack: QUndoStack | None = None


def get_stack() -> QUndoStack:
    """Return the global QUndoStack, creating it on first call."""
    global _stack
    if _stack is None:
        _stack = QUndoStack()
        _stack.setUndoLimit(100)
    return _stack


def push(command: QUndoCommand) -> None:
    """Push a command onto the undo stack."""
    get_stack().push(command)


def undo() -> None:
    """Undo the last command."""
    get_stack().undo()


def redo() -> None:
    """Redo the last undone command."""
    get_stack().redo()


def clear() -> None:
    """Clear the entire undo stack."""
    get_stack().clear()


def can_undo() -> bool:
    """Return True if there is a command to undo."""
    return get_stack().canUndo()


def can_redo() -> bool:
    """Return True if there is a command to redo."""
    return get_stack().canRedo()


def undo_text() -> str:
    """Return descriptive text for the next undo action."""
    return get_stack().undoText()


def redo_text() -> str:
    """Return descriptive text for the next redo action."""
    return get_stack().redoText()
