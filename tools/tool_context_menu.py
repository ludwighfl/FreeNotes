"""Context menu logic shared across interactive tools like Hand and Selection."""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent

def build_tool_context_menu(event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
    """Build and show right-click context menu for items or empty space."""
    pos = event.scenePos()
    
    from tools.selection_tool import _get_selectable_types
    sel_types = _get_selectable_types()
    from items.selection_overlay_item import SelectionOverlayItem
    from items.text_box_item import TextBoxItem
    from app.app_state import AppState
    
    items_at = scene.items(QRectF(pos.x() - 3, pos.y() - 3, 6, 6))
    hit_item = next(
        (i for i in items_at
         if isinstance(i, sel_types)
         and not isinstance(i, SelectionOverlayItem)),
        None,
    )

    # If hit an item not in selection, select it solely
    if hit_item and hit_item not in scene._selected_items:
        scene.set_selection([hit_item])
        
    has_clipboard = bool(AppState().items_clipboard)
    from PySide6.QtWidgets import QApplication
    sys_clipboard = QApplication.clipboard()
    can_paste = has_clipboard or bool(sys_clipboard.text()) or not sys_clipboard.image().isNull()

    menu = QMenu()
    menu.setObjectName("toolContextMenu")
    menu.setStyleSheet("""
        QMenu#toolContextMenu {
            background-color: #2d2d2d;
            border: 1px solid #3a3a3a;
            border-radius: 6px;
            padding: 4px 0;
            font-family: "Segoe UI", sans-serif;
            font-size: 13px;
        }
        QMenu#toolContextMenu::item {
            padding: 8px 32px 8px 12px;
            color: #cccccc;
        }
        QMenu#toolContextMenu::item:selected {
            background-color: #3B7BF5;
            color: #ffffff;
        }
        QMenu#toolContextMenu::item:disabled {
            color: #666666;
        }
        QMenu#toolContextMenu::separator {
            height: 1px;
            background: #3a3a3a;
            margin: 4px 8px;
        }
    """)

    if scene._selected_items:
        # 1. Item Context Menu
        
        # Skip custom menu for single textboxes - they have their own OptionsHandle popup.
        # But per the requirements, we should show this right click menu!
        # Wait, the requirements said: "Rechtsklick auf Textboxen zeigt zusätzlich: Bearbeiten".
        # Let's provide a unified menu for all.
        
        if len(scene._selected_items) == 1 and isinstance(next(iter(scene._selected_items)), TextBoxItem):
            edit_action = QAction("Bearbeiten", menu)
            edit_action.triggered.connect(lambda: next(iter(scene._selected_items)).start_editing())
            menu.addAction(edit_action)
            menu.addSeparator()

        copy_action = QAction("Kopieren\tStrg+C", menu)
        copy_action.triggered.connect(scene.copy_selected)
        menu.addAction(copy_action)

        cut_action = QAction("Ausschneiden\tStrg+X", menu)
        cut_action.triggered.connect(scene.cut_selected)
        menu.addAction(cut_action)

        menu.addSeparator()

        paste_action = QAction("Einfügen\tStrg+V", menu)
        paste_action.setEnabled(can_paste)
        paste_action.triggered.connect(scene.paste_clipboard)
        menu.addAction(paste_action)

        menu.addSeparator()

        delete_action = QAction("Löschen\tEntf", menu)
        delete_action.triggered.connect(scene.delete_selected)
        menu.addAction(delete_action)

    else:
        # 2. Empty Space Context Menu
        paste_action = QAction("Einfügen\tStrg+V", menu)
        paste_action.setEnabled(can_paste)
        paste_action.triggered.connect(scene.paste_clipboard)
        menu.addAction(paste_action)
        
        menu.addSeparator()
        
        insert_img_action = QAction("Bild einfügen ...", menu)
        insert_img_action.setEnabled(True)
        # Position image at mouse click
        insert_img_action.triggered.connect(lambda: scene.insert_image_from_file_dialog(pos))
        menu.addAction(insert_img_action)

    # Show at screen position
    screen_pos = event.screenPos()
    menu.exec(screen_pos)
