"""Context menu logic shared across interactive tools like Hand and Selection."""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication
from ui.popups.glass_menu import GlassMenu
from ui.components.icon_factory import IconFactory
from core.app_settings import AppSettings

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent


def build_tool_context_menu(event: QGraphicsSceneMouseEvent, scene: PageScene) -> None:
    """Build and show right-click context menu for items or empty space with icons."""
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
    sys_clipboard = QApplication.clipboard()
    can_paste = has_clipboard or bool(sys_clipboard.text()) or not sys_clipboard.image().isNull()

    menu = GlassMenu()
    menu.setObjectName("toolContextMenu")

    is_light = AppSettings.get_theme() == "light"
    if is_light:
        bg = "rgba(250, 250, 250, 235)"
        border = "rgba(0, 0, 0, 0.12)"
        text_color = "#222222"
        sep_color = "rgba(0, 0, 0, 0.1)"
        disabled_color = "#a0a0a0"
        icon_color = "#444444"
    else:
        bg = "rgba(28, 28, 30, 235)"
        border = "rgba(255, 255, 255, 0.14)"
        text_color = "#e5e5e7"
        sep_color = "rgba(255, 255, 255, 0.1)"
        disabled_color = "#666666"
        icon_color = "#cccccc"

    menu.setStyleSheet(f"""
        QMenu#toolContextMenu {{
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 4px;
            font-family: "Roboto", sans-serif;
            font-size: 12px;
        }}
        QMenu#toolContextMenu::item {{
            padding: 5px 22px 5px 10px;
            color: {text_color};
            border-radius: 5px;
            background: transparent;
        }}
        QMenu#toolContextMenu::item:selected {{
            background-color: #3B7BF5;
            color: #ffffff;
        }}
        QMenu#toolContextMenu::item:disabled {{
            color: {disabled_color};
        }}
        QMenu#toolContextMenu::separator {{
            height: 1px;
            background: {sep_color};
            margin: 3px 6px;
        }}
    """)

    if scene._selected_items:
        # 1. Item Context Menu
        if len(scene._selected_items) == 1 and isinstance(next(iter(scene._selected_items)), TextBoxItem):
            edit_icon = IconFactory.create("edit", color=icon_color, size=15)
            edit_action = QAction(edit_icon, "Bearbeiten", menu)
            edit_action.triggered.connect(lambda: next(iter(scene._selected_items)).start_editing())
            menu.addAction(edit_action)
            menu.addSeparator()

        copy_icon = IconFactory.create("copy", color=icon_color, size=15)
        copy_action = QAction(copy_icon, "Kopieren\tStrg+C", menu)
        copy_action.triggered.connect(scene.copy_selected)
        menu.addAction(copy_action)

        cut_icon = IconFactory.create("scissors", color=icon_color, size=15)
        cut_action = QAction(cut_icon, "Ausschneiden\tStrg+X", menu)
        cut_action.triggered.connect(scene.cut_selected)
        menu.addAction(cut_action)

        menu.addSeparator()

        rot_cw_icon = IconFactory.create("rotate_cw", color=icon_color, size=15)
        rot_cw_action = QAction(rot_cw_icon, "90° im Uhrzeigersinn", menu)
        rot_cw_action.triggered.connect(lambda: scene.rotate_selected_90(90.0))
        menu.addAction(rot_cw_action)

        rot_ccw_icon = IconFactory.create("rotate_ccw", color=icon_color, size=15)
        rot_ccw_action = QAction(rot_ccw_icon, "90° gegen Uhrzeigersinn", menu)
        rot_ccw_action.triggered.connect(lambda: scene.rotate_selected_90(-90.0))
        menu.addAction(rot_ccw_action)

        menu.addSeparator()

        paste_icon = IconFactory.create("clipboard", color=icon_color, size=15)
        paste_action = QAction(paste_icon, "Einfügen\tStrg+V", menu)
        paste_action.setEnabled(can_paste)
        paste_action.triggered.connect(lambda: scene.paste_clipboard(pos))
        menu.addAction(paste_action)

        menu.addSeparator()

        trash_icon = IconFactory.create("trash", color="#e53935", size=15)
        delete_action = QAction(trash_icon, "Löschen\tEntf", menu)
        delete_action.triggered.connect(scene.delete_selected)
        menu.addAction(delete_action)

    else:
        # 2. Empty Space Context Menu
        paste_icon = IconFactory.create("clipboard", color=icon_color, size=15)
        paste_action = QAction(paste_icon, "Einfügen\tStrg+V", menu)
        paste_action.setEnabled(can_paste)
        paste_action.triggered.connect(lambda: scene.paste_clipboard(pos))
        menu.addAction(paste_action)

        menu.addSeparator()

        img_icon = IconFactory.create("app_window", color=icon_color, size=15)
        insert_img_action = QAction(img_icon, "Bild einfügen ...", menu)
        insert_img_action.setEnabled(True)
        insert_img_action.triggered.connect(lambda: scene.insert_image_from_file_dialog(pos))
        menu.addAction(insert_img_action)

    # Show at screen position
    screen_pos = event.screenPos()
    menu.exec(screen_pos)
