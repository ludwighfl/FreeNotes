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
- **Images** — insert, move, resize, and rotate image files on the canvas
- **Selection** — rectangle and lasso multi-select; move, resize, rotate, copy/cut/paste annotations

### Document Handling
- Open and render any PDF via **PyMuPDF (fitz)** with full HiDPI support
- Asynchronous **tile-based rendering** for completely fluid zooming and panning
- Page thumbnail sidebar with drag-and-drop page reordering

### Settings & Localization
- **i18n Support**: Full internationalization for switching UI languages (German/English)
- Granular settings for Pen, Library, and Display preferences

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
├── main.py                  # Entry point
├── app/                     # Controller / Glue logic
│   ├── app_state.py         # Global reactive state (Signals, Current Document, Current Folder)
│   └── app_controller.py    # Main lifecycle, initialization, signals manager
├── core/                    # Core logic and file operations
│   ├── document_manager.py  # fitz/PyMuPDF PDF loading/rendering
│   ├── freenotes_store.py   # JSON loading/saving of annotations
│   ├── library_manager.py   # Manage PDF folder ecosystem
│   ├── zip_exporter.py      # Export `.zip` with annotated PDFs or backups
│   ├── thumbnail_cache.py   # Caching system for fast UI images
│   ├── thumbnail_worker.py  # QThread for background page rendering
│   ├── tile_renderer.py     # Asynchronous tile-based rendering for zoom performance
│   ├── tile_cache.py        # Memory management/caching for rendered PDF tiles
│   ├── i18n.py              # Internationalization and translation support
│   ├── app_settings.py      # Application preferences and config
│   ├── undo_stack.py        # Central history manager (Undo/Redo)
│   ├── shape_style.py       # Dataclass for shape formatting
│   ├── tool_style.py        # Generic styles
│   └── pdf_exporter.py      # Export JSON to PDF overlays (Orchestrator)
│       ├── pdf_text_exporter.py
│       ├── pdf_shape_exporter.py
│       ├── pdf_image_exporter.py
│       └── pdf_path_exporter.py
├── items/                   # Canvas Elements (QGraphicsItem)
│   ├── stroke_item.py       # Hand-drawn ink
│   ├── highlight_item.py    # Transparent marker
│   ├── text_box_item.py     # Text with mixins (Input, Formatting, PseudoLists)
│   ├── shape_item.py        # Geometric shapes (Ellipse, Rect, Triangles)
│   ├── image_item.py        # Inserted rasterized images
│   ├── selection_overlay_item.py # Multi-selection grouped bounding box
│   ├── handle_item.py       # Bounding box resize dots
│   ├── rotate_handle_item.py# Rotation anchor dot
│   ├── shape_handles.py     # Handle configurations for shapes
│   ├── image_handles.py     # Handle configurations for image objects
│   ├── search_highlight_item.py # Visual highlights for text search results
│   └── move_handle_item.py  # Pan controls
├── tools/                   # Interaction Handlers
│   ├── base_tool.py         # Tool Interface
│   ├── pen_tool.py          # Draws StrokeItems
│   ├── highlighter_tool.py  # Draws HighlightItems
│   ├── text_tool.py         # Spawns TextBoxItems
│   ├── shape_tool.py        # Draws geometric ShapeItems
│   ├── selection_tool.py    # Multi-item Selection & Dragging
│   ├── eraser_tool.py       # Path-based deletion tool
│   ├── hand_tool.py         # Canvas panning
│   └── tool_context_menu.py # Context menus for selections
├── commands/                # Command Pattern (Undo/Redo functionality)
│   ├── add_item_command.py, remove_item_command.py, clear_annotations_command.py
│   ├── create_shape_command.py, move_shape_command.py, rotate_shape_command.py, resize_shape_command.py
│   ├── move_image_command.py, resize_image_command.py, rotate_image_command.py
│   ├── edit_text_command.py, format_text_command.py
│   ├── rename_document_command.py
│   ├── move_items_command.py, resize_items_command.py
│   ├── modify_stroke_command.py
│   └── reorder_pages_command.py, delete_page_command.py, add_page_command.py
├── ui/                      # UI components, logically grouped
│   ├── windows/             # Top-Level Shells
│   │   ├── main_window.py
│   │   ├── manager_view.py  # Uses Mixins (manager_grid_mixin.py, manager_sidebar_mixin.py, manager_action_bar_mixin.py)
│   │   ├── settings_view.py
│   │   ├── splash_screen.py
│   │   ├── viewer_window.py # Uses Mixins (viewer_tool_manager.py, viewer_file_io.py)
│   │   └── settings_pages/  # Detail pages (display_page, language_page, library_page)
│   ├── scene/               # PDF graphics canvas and scene interaction
│   │   ├── page_view.py
│   │   ├── page_scene.py    # Uses Mixins (registry, clipboard, selection, manager, tiling, image_manager)
│   │   ├── scene_selection.py
│   │   ├── scene_clipboard.py
│   │   ├── scene_page_manager.py
│   │   ├── scene_registry.py
│   │   ├── scene_tiling.py
│   │   └── scene_image_manager.py
│   ├── bars/                # Docked toolbars and sidebars
│   │   ├── formatting_bar.py
│   │   ├── search_bar.py
│   │   ├── sidebar_widget.py
│   │   └── toolbar_widget.py
│   ├── components/          # Reusable widgets
│   │   ├── icon_factory.py
│   │   ├── pdf_card.py
│   │   ├── thumbnail_card.py
│   │   ├── editable_title_label.py
│   │   └── sidebar_item.py
│   ├── popups/              # Floating menus and dialogs
│   │   ├── color_picker_popup.py
│   │   ├── textbox_options_popup.py
│   │   ├── three_dot_menu.py
│   │   ├── new_note_dialog.py
│   │   └── zip_export_dialog.py
│   └── animations/          # QPropertyAnimation ecosystem for smooth UI transitions
│       ├── drag_reorder.py, fade.py, shadow.py, slide.py, stagger.py, thumbnail.py
├── styles/                  # qss stylesheets
│   ├── loader.py
│   ├── base.qss, toolbar.qss, formatting_bar.qss
│   └── *_light.qss          # Light appearance overrides
└── utils/                   # Shared utility functions
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
| `PageScene` | `SceneRegistryMixin`, `SceneClipboardMixin`, `SceneSelectionMixin`, `ScenePageManagerMixin`, `SceneTilingMixin`, `SceneImageManagerMixin` |
| `ViewerWindow` | `ViewerFileIOMixin`, `ViewerToolManagerMixin` |
| `ManagerView` | `ManagerGridMixin`, `ManagerSidebarMixin`, `ManagerActionBarMixin` |

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
