# FreeNotes — PDF Annotator

A professional desktop PDF annotation tool built with **Python 3.12+** and **PySide6 (Qt 6)**. FreeNotes lets you open any PDF and annotate it with freehand strokes, highlights, text boxes, and geometric shapes — all with full undo/redo support and a clean, dark-themed UI.

---

## Features

### Annotation Tools
- **Hand** — pan and scroll through the document
- **Pen** — freehand drawing with configurable color and stroke width
- **Highlighter** — Y-locked semi-transparent highlighting strokes
- **Eraser** — two modes: *Object Eraser* (removes whole items) and *Precision Eraser* (cuts into strokes and highlights pixel-precisely)
- **Text** — rich-text annotation boxes with bold, italic, underline, strikethrough, font family/size, color, and alignment
- **Shapes** — six geometric shape types drawn by click-and-drag:
  - Rectangle, Rounded Rectangle, Ellipse/Circle
  - Line, Arrow, Triangle
  - Shift-constrained proportions (squares, circles, 45°-snapped lines)
- **Selection** — rectangle and lasso multi-select; move, resize, rotate, copy/cut/paste annotations

### Document Handling
- Open and render any PDF via **PyMuPDF (fitz)** with full HiDPI support
- Page thumbnail sidebar with drag-and-drop page reordering
- Smooth zoom (fit-to-page, pinch, scroll wheel) and pan

### Save & Export
- Save/load annotations in the native `.freenotes` format (JSON-based, separate from the PDF)
- Export annotated PDFs — strokes, highlights, text boxes, and shapes are all rendered into the output PDF
- Modification indicator in the title bar (`•`)

### Undo/Redo
- Every annotation action is undoable via `Ctrl+Z` / `Ctrl+Y`
- Covers creation, deletion, movement, resizing, rotation, style changes, and text edits

---

## Requirements

- Python 3.12+
- PySide6 >= 6.6.0
- PyMuPDF >= 1.23.0

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Running the App

```bash
python main.py
```

---

## Project Structure

```
freenotes/
├── main.py                    # Entry point
├── requirements.txt
├── app/
│   └── app_state.py           # Singleton application state (tool, style, page, zoom)
├── core/                      # Domain logic — no Qt widgets
│   ├── document_manager.py    # PDF loading via PyMuPDF
│   ├── pdf_renderer.py        # Page → QPixmap with DPI scaling
│   ├── pdf_exporter.py        # PDF export orchestrator
│   ├── pdf_path_exporter.py   # Renders strokes & highlights to PDF
│   ├── pdf_text_exporter.py   # Renders text boxes to PDF
│   ├── pdf_shape_exporter.py  # Renders shapes to PDF
│   ├── freenotes_store.py     # Save/load .freenotes JSON files
│   ├── shape_style.py         # ShapeStyle dataclass + ShapeType enum
│   ├── tool_style.py          # ToolStyle dataclass (color, width, font…)
│   └── undo_stack.py          # Global undo stack
├── items/                     # QGraphicsItem subclasses (annotation objects)
│   ├── stroke_item.py         # Freehand pen strokes
│   ├── highlight_item.py      # Highlighter strokes
│   ├── text_box_item.py       # Rich-text annotation boxes
│   ├── shape_item.py          # Geometric shapes (6 types)
│   ├── shape_handles.py       # Shape-specific resize/move/rotate handles
│   ├── handle_item.py         # Base resize handle
│   ├── move_handle_item.py    # Drag-to-move handle pill
│   ├── rotate_handle_item.py  # Rotation handle
│   ├── options_handle_item.py # Copy/Cut/Delete options bar
│   ├── selection_overlay_item.py  # Multi-selection visual overlay
│   └── bounding_box_handle_manager.py  # Unified resize for multi-selection
├── tools/                     # Tool implementations (Strategy pattern)
│   ├── base_tool.py
│   ├── hand_tool.py
│   ├── pen_tool.py
│   ├── highlighter_tool.py
│   ├── eraser_tool.py
│   ├── text_tool.py
│   ├── shape_tool.py
│   └── selection_tool.py
├── commands/                  # Undo/Redo commands (Command pattern)
│   └── *.py                   # One command class per user action
├── ui/                        # Qt widgets
│   ├── main_window.py
│   ├── viewer_window.py       # Main PDF viewer (uses mixins)
│   ├── viewer_file_io.py      # File I/O mixin (open, save, export)
│   ├── viewer_tool_manager.py # Tool & style routing mixin
│   ├── page_scene.py          # QGraphicsScene — layout + event dispatch
│   ├── scene_registry.py      # Per-page item tracking mixin
│   ├── scene_clipboard.py     # Copy/cut/paste + serialization mixin
│   ├── page_view.py           # QGraphicsView — zoom, scroll, viewport
│   ├── toolbar_widget.py      # Tool selection, colors, stroke widths
│   ├── formatting_bar.py      # Rich-text formatting bar
│   ├── sidebar_widget.py      # Page thumbnail sidebar
│   └── ...                    # Popups, dialogs, icon factory
├── styles/                    # QSS stylesheets
│   └── *.qss
└── utils/
    └── path_helpers.py        # PyInstaller-compatible path resolution
```

---

## Architecture

FreeNotes follows a layered architecture with four primary design patterns:

**Singleton — `AppState`**
Global state for the active tool, style (color, width, font), current page, zoom, and clipboard. All components interact through `AppState()` and react to its Qt Signals.

**Command Pattern — `commands/`**
Every user action that modifies an annotation is wrapped in a command with `redo()` and `undo()`. Commands are pushed to the global undo stack and store only the minimal before/after state needed to reverse the action.

**Strategy Pattern — `tools/`**
`PageScene` holds one active `BaseTool`. Mouse events are delegated to the current tool via `on_press()`, `on_move()`, and `on_release()`. Switching tools simply replaces the strategy.

**Mixin Pattern**
Large classes are decomposed into focused pure-Python mixins to keep file sizes manageable and responsibilities separated. Mixins must not inherit from `QObject`.

| Class | Mixins |
|-------|--------|
| `TextBoxItem` | `TextBoxInputMixin`, `TextBoxFormattingMixin`, `TextBoxPseudoListMixin` |
| `PageScene` | `SceneRegistryMixin`, `SceneClipboardMixin` |
| `ViewerWindow` | `ViewerFileIOMixin`, `ViewerToolManagerMixin` |

---

## Conventions

| Area | Convention |
|------|------------|
| Language | UI strings in German; code and comments in English |
| Naming | `snake_case` for files/methods, `PascalCase` for classes |
| Coordinates | Items use local coords (`setPos(topLeft)`, `_rect = QRectF(0, 0, w, h)`) |
| Z-values | PDF pages: 0 · Highlights: 5 · Strokes: 10 · Text/Shapes: 15 · Eraser cursor: 20 |
| File size | Target ≤ 300 lines per file; split with mixins if exceeded |

---

## File Formats

### `.freenotes`
A JSON file that stores all annotations for a given PDF. It records the path to the associated PDF and serializes every annotation (strokes, highlights, text boxes, shapes) on a per-page basis. The PDF itself is never modified when saving a `.freenotes` file.

### PDF Export
The export pipeline renders each annotation type on top of the original PDF pages using PyMuPDF and produces a new, self-contained PDF file. The original PDF is never overwritten.
