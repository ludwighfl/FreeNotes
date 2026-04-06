"""Mixin for ManagerView Grid Logic."""

from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from ui.components.icon_factory import IconFactory
from ui.components.pdf_card import PdfCard

if TYPE_CHECKING:
    pass

class ManagerGridMixin:
    """Provides grid loading and display logic for ManagerView."""

    def load_grid(self, folder: Path | None) -> None:
        from app.app_state import AppState
        lm = AppState().library_manager
        if lm is None:
            return

        AppState().current_folder = folder

        if folder is None:
            self._folder_title.setText("Alle Dokumente")
        else:
            self._folder_title.setText(folder.name)

        docs = lm.get_documents_recursive(folder)
        self._search_input.clear()
        self._all_docs = docs
        self._display_docs(docs)

    def _display_docs(self, docs: list[dict]) -> None:
        self._clear_grid()

        if not docs:
            self._show_empty_state()
            return
        self._hide_empty_state()

        for i, doc in enumerate(docs):

            card = PdfCard(
                pdf_path=doc["pdf"],
                freenotes_path=doc["freenotes"],
                name=doc["name"],
                modified=doc["modified"],
                thumbnail_cache=self._thumbnail_cache,
            )
            card.double_clicked.connect(self._on_card_double_clicked)
            card.rename_requested.connect(
                lambda name, d=doc: self._on_rename(d, name))
            card.delete_requested.connect(
                lambda d=doc: self._on_delete(d))
            row = i // 4
            col = i % 4
            self._grid_layout.addWidget(card, row, col)
            self._cards.append(card)

        # Stagger animate the new cards
        from ui.animations import StaggerFadeAnimation
        self._stagger_anim = StaggerFadeAnimation(self._cards, delay_ms=20, max_total_ms=400)
        self._stagger_anim.start()

        QTimer.singleShot(50, self._check_visible_cards)

    def _load_recent_grid(self) -> None:
        from core.app_settings import AppSettings

        self._folder_title.setText("Zuletzt geöffnet")
        self._search_input.clear()

        paths = AppSettings.get_last_opened()
        docs: list[dict] = []
        for p_str in paths:
            p = Path(p_str)
            if not p.exists():
                continue
            pdf = p.with_suffix(".pdf")
            docs.append({
                "pdf": pdf if pdf.exists() else None,
                "freenotes": p,
                "name": p.stem,
                "modified": p.stat().st_mtime,
                "folder": p.parent,
            })
        self._all_docs = docs
        self._display_docs(docs)

    def _clear_grid(self) -> None:
        if hasattr(self, "_multi_select_mode"):
            self._multi_select_mode = False
        if hasattr(self, "clear_selection"):
            self.clear_selection()
            
        for card in self._cards:
            self._grid_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    def _check_visible_cards(self) -> None:
        """Check which cards are visible and start progressive rendering."""
        if not self._cards:
            return
        viewport_rect = self._scroll.viewport().rect()
        vp_global = self._scroll.viewport().mapToGlobal(QPoint(0, 0))

        for card in self._cards:
            if card._rendered:
                continue
            card_global = card.mapToGlobal(QPoint(0, 0))
            rel = card_global - vp_global
            card_rect = card.rect().translated(rel.x(), rel.y())
            if viewport_rect.intersects(card_rect):
                card.render_if_needed()
                # Yield to event loop after each render for smooth UI
                QTimer.singleShot(0, self._check_visible_cards)
                return

    def _show_empty_state(self) -> None:
        if not hasattr(self, "_empty_container"):
            # Create overlay widget parented to scroll viewport
            self._empty_container = QWidget(self._scroll.viewport())
            self._empty_container.setObjectName("emptyState")
            self._empty_container.setStyleSheet(
                "QWidget#emptyState { background: transparent; }")
            empty_layout = QVBoxLayout(self._empty_container)
            empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.setSpacing(12)

            icon_lbl = QLabel()
            icon_lbl.setPixmap(
                IconFactory.create_pixmap(
                    "folder_x", color="#444444", size=64))
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setStyleSheet("background: transparent;")
            empty_layout.addWidget(icon_lbl)

            title_lbl = QLabel("Keine Dokumente")
            title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_lbl.setStyleSheet(
                "color: #555555; font-size: 18px; font-weight: bold;"
                " background: transparent;")
            empty_layout.addWidget(title_lbl)

            desc_lbl = QLabel("Importiere ein PDF über 'Erstellen'")
            desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc_lbl.setStyleSheet(
                "color: #444444; font-size: 13px;"
                " background: transparent;")
            empty_layout.addWidget(desc_lbl)
        # Size to fill the entire viewport and raise above grid
        vp = self._scroll.viewport()
        self._empty_container.setGeometry(vp.rect())
        self._empty_container.raise_()
        self._empty_container.setVisible(True)

    def _hide_empty_state(self) -> None:
        if hasattr(self, "_empty_container"):
            self._empty_container.setVisible(False)
