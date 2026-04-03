# FreeNotes Architecture

Das Projekt ist konsequent in Module unterteilt. Kern-Logik und Datenstrukturen (`core`) sind streng von der UI (`ui`) und den Canvas-Elementen (`items`) getrennt. Alle Interaktionen auf dem PDF-Canvas werden über dedizierte Tools (`tools`) gehandhabt.

Dieses Design folgt lose dem Model-View-Controller/Presenter (MVC) Pattern.

## Directory Map

```text
c:\Users\ludwi\.gemini\antigravity\scratch\pdf_annotator
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
│   ├── app_settings.py      # Application preferences and config
│   ├── undo_stack.py        # Central history manager (Undo/Redo)
│   ├── shape_style.py       # Dataclass for shape formatting
│   ├── tool_style.py        # Generic styles
│   └── pdf_exporter.py      # Export JSON to PDF overlays (Orchestrator)
│       ├── pdf_text_exporter.py
│       ├── pdf_shape_exporter.py
│       └── pdf_path_exporter.py
├── items/                   # Canvas Elements (QGraphicsItem)
│   ├── stroke_item.py       # Hand-drawn ink
│   ├── highlight_item.py    # Transparent marker
│   ├── text_box_item.py     # Text with mixins (Input, Formatting, PseudoLists)
│   ├── shape_item.py        # Geometric shapes (Ellipse, Rect, Triangles)
│   ├── selection_overlay_item.py # Multi-selection grouped bounding box
│   ├── handle_item.py       # Bounding box resize dots
│   ├── rotate_handle_item.py# Rotation anchor dot
│   ├── shape_handles.py     # Handle configurations for shapes
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
│   └── hand_tool.py         # Canvas panning
├── commands/                # Command Pattern (Undo/Redo functionality)
│   ├── add_item_command.py, remove_item_command.py
│   ├── create_shape_command.py, move_shape_command.py, rotate_shape_command.py, resize_shape_command.py
│   ├── edit_text_command.py, format_text_command.py
│   ├── move_items_command.py, resize_items_command.py
│   ├── modify_stroke_command.py
│   └── reorder_pages_command.py, delete_page_command.py, add_page_command.py
├── ui/                      # UI components, logically grouped
│   ├── windows/             # Top-Level Shells
│   │   ├── main_window.py
│   │   ├── manager_view.py
│   │   ├── settings_view.py
│   │   ├── splash_screen.py
│   │   ├── viewer_window.py # Uses Mixins (viewer_tool_manager.py, viewer_file_io.py)
│   │   └── settings_pages/  # Detail pages (display_page, language_page, library_page)
│   ├── scene/               # PDF graphics canvas and scene interaction
│   │   ├── page_view.py
│   │   ├── page_scene.py    # Uses Mixins (scene_registry.py, scene_page_manager.py)
│   │   ├── scene_selection.py
│   │   └── scene_clipboard.py
│   ├── bars/                # Docked toolbars and sidebars
│   │   ├── formatting_bar.py
│   │   ├── search_bar.py
│   │   ├── sidebar_widget.py
│   │   └── toolbar_widget.py
│   ├── components/          # Reusable widgets
│   │   ├── icon_factory.py
│   │   ├── pdf_card.py
│   │   ├── thumbnail_card.py
│   │   └── sidebar_item.py
│   ├── popups/              # Floating menus and dialogs
│   │   ├── color_picker_popup.py
│   │   ├── textbox_options_popup.py
│   │   ├── three_dot_menu.py
│   │   └── zip_export_dialog.py
│   └── animations/          # QPropertyAnimation ecosystem for smooth UI transitions
│       ├── drag_reorder.py, fade.py, shadow.py, slide.py, stagger.py, thumbnail.py
├── styles/                  # qss stylesheets
│   ├── loader.py
│   ├── base.qss, toolbar.qss, formatting_bar.qss
│   └── *_light.qss          # Light appearance overrides
└── utils/                   # Shared utility functions
```

## The Mixin Pattern

Da Qt keine Multiple-Inheritance von `QObject` Klassen erlaubt (z.B. kann eine Klasse nicht von `QGraphicsItem` *und* `QWidget` erben), verwenden wir das **Mixin Pattern** für große/überladene Qt-Klassen. 
Das bedeutet, wir lagern Logik-Blöcke in reine Python-Objekt-Klassen aus (`class SomethingMixin:`), von denen unsere Haupt-Qt-Klasse (z.B. `ViewerWindow`) dann zusätzlich erbt. So bleiben die Dateien klein und übersichtlich.

| Class | Mixins | Qt Base |
|-------|--------|---------|
| `TextBoxItem` | `TextBoxInputMixin`, `TextBoxFormattingMixin`, `TextBoxPseudoListMixin` | `QGraphicsObject` |
| `PageScene` | `SceneRegistryMixin`, `SceneClipboardMixin`, `SceneSelectionMixin`, `ScenePageManagerMixin` | `QGraphicsScene` |
| `ToolbarWidget` | `ToolbarModePopupsMixin` | `QWidget` |
| `ViewerWindow` | `ViewerFileIOMixin`, `ViewerToolManagerMixin` | `QWidget` |

## Code Guidelines
- **No file > 650 lines of code.** Extrahieren von Sub-Klassen oder Mixins, sobald eine UI-Datei zu monströs wird.
- **Dependency Inversion**: UI Klassen sollten den `core` anfragen, der `core` sollte niemals in der UI herumpfuschen.
- Pydantic/Type Hints (`-> None`, etc.) konsequent nutzen, für Auto-Complete und Clean Code.
- Undo/Redo wird **ausschließlich** über den `core/undo_stack.py` mit separaten `QUndoCommand` Klassen im Ordner `commands/` abgewickelt.
