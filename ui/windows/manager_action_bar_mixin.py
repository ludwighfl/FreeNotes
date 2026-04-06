"""Mixin for ManagerView Action Bar and Selection Logic."""

from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QToolButton,
    QStackedWidget, QMessageBox, QInputDialog, QFileDialog
)
from PySide6.QtGui import QFont

from ui.components.icon_factory import IconFactory

if TYPE_CHECKING:
    from ui.components.pdf_card import PdfCard


class ManagerActionBarMixin:
    """Provides action bar and selection logic for ManagerView."""

    def init_action_bar(self, header_layout: QHBoxLayout) -> None:
        """Initialize the multi-state header (Default vs Action Bar)."""
        self._selection: set[PdfCard] = set()
        self._multi_select_mode = False

        # Stack to switch between normal header and action bar
        self._header_stack = QStackedWidget()
        self._header_stack.setFixedHeight(40)
        
        # --- State 1: Default Header ---
        self._default_header = QWidget()
        default_layout = QHBoxLayout(self._default_header)
        default_layout.setContentsMargins(0, 0, 0, 0)
        
        self._folder_title = QLabel("Alle Dokumente")
        self._folder_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self._folder_title.setStyleSheet("color: #ffffff;")
        default_layout.addWidget(self._folder_title)
        default_layout.addStretch()
        
        # We inject the existing right-side widgets (Search, Create, Settings)
        # after this method is called.
        self._default_header_right_layout = QHBoxLayout()
        default_layout.addLayout(self._default_header_right_layout)

        # --- State 2: Action Bar ---
        self._action_bar = QWidget()
        self._action_bar.setObjectName("actionBar")
        self._action_bar.setStyleSheet("""
            QWidget#actionBar {
                background: #3B7BF5; 
                border-radius: 6px;
            }
        """)
        action_layout = QHBoxLayout(self._action_bar)
        action_layout.setContentsMargins(8, 4, 16, 4)
        action_layout.setSpacing(12)

        # Cancel Selection Button
        btn_cancel = QToolButton()
        btn_cancel.setIcon(IconFactory.create("x", color="#ffffff", size=18))
        btn_cancel.setStyleSheet("background: transparent; border: none;")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.clear_selection)
        action_layout.addWidget(btn_cancel)

        # Selection Count Label
        self._selection_count_lbl = QLabel("1 ausgewählt")
        self._selection_count_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._selection_count_lbl.setStyleSheet("color: #ffffff; background: transparent;")
        action_layout.addWidget(self._selection_count_lbl)
        
        action_layout.addStretch()

        # Action Buttons
        self._btn_rename = self._create_action_btn("pen", "Umbenennen", self._on_action_rename)
        self._btn_duplicate = self._create_action_btn("copy", "Duplizieren", self._on_action_duplicate)
        self._btn_export = self._create_action_btn("download", "Exportieren", self._on_action_export)
        self._btn_delete = self._create_action_btn("trash", "Löschen", self._on_action_delete)

        action_layout.addWidget(self._btn_rename)
        action_layout.addWidget(self._btn_duplicate)
        action_layout.addWidget(self._btn_export)
        action_layout.addWidget(self._btn_delete)

        self._header_stack.addWidget(self._default_header)
        self._header_stack.addWidget(self._action_bar)
        header_layout.addWidget(self._header_stack)

    def _create_action_btn(self, icon_name: str, tooltip: str, callback: object) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(IconFactory.create(icon_name, color="#ffffff", size=18))
        btn.setToolTip(tooltip)
        btn.setStyleSheet("""
            QToolButton {
                background: transparent; border: none; border-radius: 4px; padding: 4px;
            }
            QToolButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
        """)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(callback)
        return btn

    def toggle_multi_select(self) -> None:
        self._multi_select_mode = not self._multi_select_mode
        self.clear_selection()
        for card in getattr(self, "_cards", []):
            card.set_checkbox_visible(self._multi_select_mode)

    def is_multi_select_mode(self) -> bool:
        return self._multi_select_mode

    def clear_selection(self) -> None:
        import shiboken6
        for card in list(self._selection):
            if shiboken6.isValid(card):
                card.set_selected(False)
        self._selection.clear()
        self._update_action_bar()

    def handle_card_click(self, card: PdfCard) -> None:
        if self._multi_select_mode:
            if card in self._selection:
                self._selection.remove(card)
                card.set_selected(False)
            else:
                self._selection.add(card)
                card.set_selected(True)
        else:
            if card in self._selection:
                self.clear_selection()
            else:
                self.clear_selection()
                self._selection.add(card)
                card.set_selected(True)
            
        self._update_action_bar()

    def _update_action_bar(self) -> None:
        count = len(self._selection)
        if count == 0:
            self._header_stack.setCurrentIndex(0)
            return

        self._header_stack.setCurrentIndex(1)
        self._selection_count_lbl.setText(f"{count} ausgewählt")
        
        # Rename is only viable for single selection
        self._btn_rename.setVisible(count == 1)

    # --- Actions ---

    def _get_selected_docs(self) -> list[dict]:
        # Filter safely to ensure we don't access deleted objects
        import shiboken6
        docs = []
        for card in list(self._selection):
            if shiboken6.isValid(card):
                docs.append(card.get_doc_data())
        return docs

    def _on_action_rename(self) -> None:
        docs = self._get_selected_docs()
        if len(docs) != 1: return
        doc = docs[0]
        
        name, ok = QInputDialog.getText(
            self, "Umbenennen", "Neuer Name:", text=doc.get("name", ""))
        self.clear_selection()
        if ok and name.strip():
            # Uses manager_view's existing rename handler
            self._on_rename(doc, name.strip())

    def _on_action_delete(self) -> None:
        docs = self._get_selected_docs()
        if not docs: return
        
        text = f'"{docs[0].get("name")}"' if len(docs) == 1 else f"{len(docs)} Dokumente"
        reply = QMessageBox.question(
            self, "Löschen",
            f'{text} in den Papierkorb verschieben?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
        self.clear_selection()
        if reply == QMessageBox.StandardButton.Yes:
            for doc in docs:
                self._on_delete(doc) # Existing delete handler

    def _on_action_duplicate(self) -> None:
        docs = self._get_selected_docs()
        if not docs: return
        
        self.clear_selection()
        from app.app_state import AppState
        lm = AppState().library_manager
        if lm:
            for doc in docs:
                lm.duplicate_document(doc)
            self.load_grid(AppState().current_folder)



    def _on_action_export(self) -> None:
        docs = self._get_selected_docs()
        if not docs: return
        
        from core.pdf_exporter import PdfExporter
        from core.document_manager import DocumentManager
        from ui.scene.page_scene import PageScene
        from core.freenotes_store import FreenotesStore
        from pathlib import Path
        
        if len(docs) == 1:
            # Single Export (PDF)
            doc = docs[0]
            out_file, _ = QFileDialog.getSaveFileName(
                self, "Exportieren", f"{doc.get('name')}_annotated.pdf", "PDF Dateien (*.pdf)")
            self.clear_selection()
            if out_file:
                pdf_path = doc.get("pdf")
                fn_path = doc.get("freenotes")
                if pdf_path and pdf_path.exists():
                    dm = DocumentManager()
                    dm.open_document(pdf_path)
                    scene = PageScene()
                    scene.load_document(dm)
                    if fn_path and fn_path.exists():
                        FreenotesStore.load(str(fn_path), scene, dm)
                        
                    exporter = PdfExporter(scene, dm)
                    exporter.export(str(pdf_path), out_file)
                    
                QMessageBox.information(self, "Export", "Erfolgreich exportiert.")
        else:
            # Multi Export (ZIP)
            out_file, _ = QFileDialog.getSaveFileName(self, "Exportieren als ZIP", "export.zip", "ZIP Dateien (*.zip)")
            self.clear_selection()
            if out_file:
                import zipfile
                from PySide6.QtWidgets import QProgressDialog
                import tempfile
                
                progress = QProgressDialog("Exportiere Dokumente...", "Abbrechen", 0, len(docs), self)
                progress.setWindowModality(Qt.WindowModality.WindowModal)
                
                try:
                    with zipfile.ZipFile(out_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for i, doc in enumerate(docs):
                            if progress.wasCanceled():
                                break
                            progress.setValue(i)
                            
                            pdf_path = doc.get("pdf")
                            fn_path = doc.get("freenotes")
                            if not pdf_path or not pdf_path.exists():
                                continue

                            dm = DocumentManager()
                            dm.open_document(pdf_path)
                            scene = PageScene()
                            scene.load_document(dm)
                            if fn_path and fn_path.exists():
                                FreenotesStore.load(str(fn_path), scene, dm)
                                
                            exporter = PdfExporter(scene, dm)
                            
                            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                                tmp_path = Path(tmp.name)
                            
                            exporter.export(str(pdf_path), str(tmp_path))
                            
                            zip_name = f"{doc.get('name')}.pdf"
                            zipf.write(tmp_path, zip_name)
                            tmp_path.unlink()
                            
                    progress.setValue(len(docs))
                    if not progress.wasCanceled():
                        QMessageBox.information(self, "Export", "Erfolgreich als ZIP exportiert.")
                except Exception as e:
                    QMessageBox.warning(self, "Fehler", f"Export fehlgeschlagen: {e}")
