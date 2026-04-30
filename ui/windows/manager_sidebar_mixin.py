"""Mixin for ManagerView Sidebar Logic."""

from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QMenu, QInputDialog, QMessageBox
)

from ui.components.icon_factory import IconFactory
from core.i18n import tr

if TYPE_CHECKING:
    pass

class ManagerSidebarMixin:
    """Provides sidebar tree logic for ManagerView."""

    def load_sidebar(self) -> None:
        """Populate the folder sidebar from LibraryManager."""
        from app.app_state import AppState
        lm = AppState().library_manager
        if lm is None:
            return

        # Clear existing items
        for w in self._sidebar_widgets:
            self._sidebar_layout.removeWidget(w)
            w.deleteLater()
        self._sidebar_widgets.clear()

        # "Alle Dokumente"
        all_item = self._make_sidebar_item(
            icon_name="layout_grid",
            text=tr("manager.all_documents"),
            indent=0,
            active=(self._active_folder is None
                    and self._active_mode != "recent"),
            on_click=lambda: self._select_folder(None))
        self._sidebar_layout.insertWidget(
            self._sidebar_layout.count() - 1, all_item)
        self._sidebar_widgets.append(all_item)

        # "Zuletzt geöffnet"
        from core.app_settings import AppSettings
        if AppSettings.get_last_opened():
            recent_item = self._make_sidebar_item(
                icon_name="clock",
                text=tr("manager.recent"),
                indent=0,
                active=(self._active_mode == "recent"),
                on_click=self._select_recent)
            self._sidebar_layout.insertWidget(
                self._sidebar_layout.count() - 1, recent_item)
            self._sidebar_widgets.append(recent_item)

        # Recursive folder tree
        self._add_folders_to_sidebar(lm.root, depth=0)

    def _add_folders_to_sidebar(
        self, parent: Path, depth: int
    ) -> None:
        from app.app_state import AppState
        lm = AppState().library_manager
        if lm is None:
            return

        for folder in lm.get_folders(parent):
            is_expanded = folder in self._expanded_folders
            is_active = folder == self._active_folder

            chevron = "chevron_down" if is_expanded else "chevron_right"
            icon_name = "folder_open" if is_expanded else "folder"

            item = self._make_sidebar_item(
                icon_name=icon_name,
                text=folder.name,
                indent=depth,
                active=is_active,
                on_click=lambda f=folder: self._toggle_folder(f),
                chevron_name=chevron,
                on_context_menu=lambda pos, widget, f=folder: self._show_folder_context_menu(pos, widget, f))
            self._sidebar_layout.insertWidget(
                self._sidebar_layout.count() - 1, item)
            self._sidebar_widgets.append(item)

            if is_expanded:
                self._add_folders_to_sidebar(folder, depth + 1)

    def _show_folder_context_menu(self, pos: QPoint, widget: QWidget, folder: Path) -> None:
        """Show context menu for a folder in the sidebar."""
        menu = QMenu()
        menu.setObjectName("pageContextMenu")
        menu.addAction(tr("menu.rename", "Umbenennen"), lambda: self._on_rename_folder_action(folder))
        menu.addSeparator()
        menu.addAction(tr("menu.delete", "Löschen"), lambda: self._on_delete_folder_action(folder))
        
        global_pos = widget.mapToGlobal(pos)
        menu.exec(global_pos)
            
    def _on_rename_folder_action(self, folder: Path) -> None:
        from core.app_settings import AppSettings
        from app.app_state import AppState
        lm = AppState().library_manager
        if not lm:
            return
            
        new_name, ok = QInputDialog.getText(
            self, "Ordner umbenennen", "Neuer Name:", text=folder.name)
        if ok and new_name.strip() and new_name.strip() != folder.name:
            try:
                new_folder = lm.rename_folder(folder, new_name.strip())
                # Update expanded folders
                if folder in self._expanded_folders:
                    self._expanded_folders.remove(folder)
                    self._expanded_folders.add(new_folder)
                
                # Check for active replacement
                if self._active_folder == folder:
                    self._select_folder(new_folder)
                else:
                    self.load_sidebar()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))
                
    def _on_delete_folder_action(self, folder: Path) -> None:
        from app.app_state import AppState
        lm = AppState().library_manager
        if not lm:
            return
            
        # Check if empty
        try:
            docs = lm.get_documents(folder)
            subfolders = lm.get_all_folders(folder)
            
            if docs or subfolders:
                reply = QMessageBox.question(
                    self, "Ordner löschen",
                    f'Der Ordner "{folder.name}" enthält Dokumente oder Unterordner.\nWirklich in den Papierkorb verschieben?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if reply != QMessageBox.StandardButton.Yes:
                    return
            
            lm.delete_folder(folder)
            
            if folder in self._expanded_folders:
                self._expanded_folders.remove(folder)
                
            if self._active_folder and str(self._active_folder).startswith(str(folder)):
                self._select_folder(None) # Fallback to Root
            else:
                self.load_sidebar()
                
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Konnte Ordner nicht löschen: {e}")

    def _make_sidebar_item(
        self,
        icon_name: str,
        text: str,
        indent: int,
        active: bool,
        on_click: object,
        chevron_name: str | None = None,
        on_context_menu: object | None = None,
    ) -> QWidget:
        """Create a clickable sidebar item widget."""
        item = QWidget()
        item.setObjectName("sidebarItem")
        item.setFixedHeight(32)
        item.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(item)
        layout.setContentsMargins(8 + indent * 16, 4, 8, 4)
        layout.setSpacing(6)

        # Define Icon Color (Dark/Light aware - mostly handled by IconFactory if we pass neutral, but we need it here)
        from core.app_settings import AppSettings
        is_light = AppSettings.get_theme() == "light"
        
        if active:
            color = "#ffffff"
        else:
            color = "#666666" if is_light else "#cccccc"
            
        if chevron_name:
            chev_lbl = QLabel()
            chev_lbl.setPixmap(IconFactory.create(chevron_name, color=color, size=14).pixmap(14, 14))
            chev_lbl.setFixedSize(14, 14)
            chev_lbl.setObjectName("sidebarIcon")
            layout.addWidget(chev_lbl)
        elif indent >= 0:
            # Align items without chevrons
            layout.addSpacing(14)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(
            IconFactory.create(icon_name, color=color, size=16).pixmap(16, 16))
        icon_lbl.setFixedSize(16, 16)
        icon_lbl.setObjectName("sidebarIcon")

        text_lbl = QLabel()
        text_lbl.setObjectName("sidebarItemText")
        
        # Calculate available width to elide text
        # Sidebar is 280px. Margins and icons take up roughly 90px + indent * 16px.
        from PySide6.QtGui import QFont, QFontMetrics
        available_w = max(40, 190 - (indent * 16))
        metrics = QFontMetrics(QFont("Segoe UI", 10))
        elided_text = metrics.elidedText(text, Qt.TextElideMode.ElideRight, available_w)
        text_lbl.setText(elided_text)
        text_lbl.setToolTip(text)

        layout.addWidget(icon_lbl)
        layout.addWidget(text_lbl, 1)

        item.setProperty("active", active)

        def _handle_mouse_press(e):
            if e.button() == Qt.MouseButton.LeftButton:
                on_click()
            QWidget.mousePressEvent(item, e)
            
        item.mousePressEvent = _handle_mouse_press
        
        if on_context_menu:
            item.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            item.customContextMenuRequested.connect(lambda pos: on_context_menu(pos, item))
            
        return item

    def _toggle_folder(self, folder: Path) -> None:
        if folder in self._expanded_folders:
            self._expanded_folders.discard(folder)
            
            # 7.2 Recursive collapse
            from app.app_state import AppState
            lm = AppState().library_manager
            if lm is not None:
                all_sub = lm.get_all_folders(folder)
                self._expanded_folders.difference_update(all_sub)
        else:
            self._expanded_folders.add(folder)
        self._select_folder(folder)

    def _select_folder(self, folder: Path | None) -> None:
        self._active_folder = folder
        self._active_mode = "folder"
        self.load_sidebar()
        self.load_grid(folder)

    def _select_recent(self) -> None:
        self._active_mode = "recent"
        self._active_folder = None
        self.load_sidebar()
        self._load_recent_grid()
