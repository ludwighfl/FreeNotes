"""FreeNotes file store – save/load .freenotes JSON annotation files."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath, QColor

from core.document_manager import DocumentManager
from core.tool_style import ToolStyle
from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem
from items.text_box_item import TextBoxItem
from items.shape_item import ShapeItem

if TYPE_CHECKING:
    from ui.page_scene import PageScene


class FreenotesStore:
    """Stateless utility class for saving/loading .freenotes files."""

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    @classmethod
    def save(cls, path: str, scene: PageScene, doc_manager: DocumentManager) -> None:
        """Save all annotations from *scene* to a .freenotes JSON file."""
        
        pdf_path = ""
        # Save a companion PDF so structural changes (pages added/removed/reordered) are persisted.
        pdf_filename = os.path.basename(path).replace(".freenotes", ".pdf")
        if pdf_filename == os.path.basename(path):
            pdf_filename += ".pdf"
            
        companion_pdf_path = os.path.join(os.path.dirname(path), pdf_filename)
        if doc_manager.save_document_copy(companion_pdf_path):
            pdf_path = companion_pdf_path
            
        data: dict = {
            "version": 1,
            "pdf_path": pdf_path,
            "pages": {},
        }

        # Collect all page indices with annotations
        all_pages: set[int] = set()
        all_pages.update(scene._stroke_items.keys())
        all_pages.update(scene._highlight_items.keys())
        all_pages.update(scene._text_box_items.keys())
        all_pages.update(scene._shape_items.keys())

        for page_idx in sorted(all_pages):
            page_data: dict = {
                "strokes": [],
                "highlights": [],
                "textboxes": [],
                "shapes": [],
            }

            for item in scene._stroke_items.get(page_idx, []):
                page_data["strokes"].append(cls._serialize_stroke(item))

            for item in scene._highlight_items.get(page_idx, []):
                page_data["highlights"].append(cls._serialize_highlight(item))

            for item in scene._text_box_items.get(page_idx, []):
                page_data["textboxes"].append(cls._serialize_textbox(item))

            for item in scene._shape_items.get(page_idx, []):
                page_data["shapes"].append(item.to_dict())

            # Skip pages with no annotations
            if any(v for v in page_data.values()):
                data["pages"][str(page_idx)] = page_data

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str, scene: PageScene) -> str:
        """Load annotations from a .freenotes file into *scene*.

        Returns the stored pdf_path.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        pdf_path: str = data.get("pdf_path", "")

        # Clear existing annotations
        cls._clear_scene_annotations(scene)

        for page_str, page_data in data.get("pages", {}).items():
            page_idx = int(page_str)

            for d in page_data.get("strokes", []):
                try:
                    item = cls._deserialize_stroke(d, page_idx)
                    scene.addItem(item)
                    scene.add_item_to_registry(item)
                except Exception as e:
                    print(f"Warning: Stroke laden fehlgeschlagen: {e}")

            for d in page_data.get("highlights", []):
                try:
                    item = cls._deserialize_highlight(d, page_idx)
                    scene.addItem(item)
                    scene.add_item_to_registry(item)
                except Exception as e:
                    print(f"Warning: Highlight laden fehlgeschlagen: {e}")

            for d in page_data.get("textboxes", []):
                try:
                    item = cls._deserialize_textbox(d, page_idx)
                    scene.addItem(item)
                    scene.add_item_to_registry(item)
                except Exception as e:
                    print(f"Warning: Textbox laden fehlgeschlagen: {e}")

            for d in page_data.get("shapes", []):
                try:
                    item = ShapeItem.from_dict(d)
                    scene.addItem(item)
                    scene.add_item_to_registry(item)
                except Exception as e:
                    print(f"Warning: Shape laden fehlgeschlagen: {e}")

        return pdf_path

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    @classmethod
    def _clear_scene_annotations(cls, scene: PageScene) -> None:
        """Remove all annotation items from the scene."""
        for item in list(scene.items()):
            if isinstance(item, (StrokeItem, HighlightItem,
                                 TextBoxItem, ShapeItem)):
                scene.removeItem(item)

        scene._stroke_items.clear()
        scene._highlight_items.clear()
        scene._text_box_items.clear()
        scene._shape_items.clear()

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    @classmethod
    def resolve_pdf_path(cls, pdf_path: str, freenotes_path: str) -> str:
        """Resolve the PDF path, trying relative to .freenotes if absolute fails."""
        if os.path.isabs(pdf_path) and os.path.exists(pdf_path):
            return pdf_path
        # Try relative to .freenotes file
        base_dir = os.path.dirname(os.path.abspath(freenotes_path))
        relative = os.path.join(base_dir, os.path.basename(pdf_path))
        if os.path.exists(relative):
            return relative
        return pdf_path  # Fallback: return original

    # ------------------------------------------------------------------
    # Serialization helpers (matching scene_clipboard.py patterns)
    # ------------------------------------------------------------------

    @classmethod
    def _serialize_stroke(cls, item: StrokeItem) -> dict:
        path = item._path
        points = []
        for i in range(path.elementCount()):
            el = path.elementAt(i)
            points.append((el.x, el.y))
        return {
            "type": "stroke",
            "points": points,
            "color": item._style.color.name(),
            "width": item._style.width,
            "page_index": item.page_index,
            "pos": (item.pos().x(), item.pos().y()),
        }

    @classmethod
    def _serialize_highlight(cls, item: HighlightItem) -> dict:
        path = item._path
        points = []
        for i in range(path.elementCount()):
            el = path.elementAt(i)
            points.append((el.x, el.y))
        return {
            "type": "highlight",
            "points": points,
            "color": item._style.color.name(),
            "width": item._style.width,
            "page_index": item._page_index,
            "pos": (item.pos().x(), item.pos().y()),
        }

    @classmethod
    def _serialize_textbox(cls, item: TextBoxItem) -> dict:
        r = item.get_rect()
        return {
            "type": "textbox",
            "html": item._document.toHtml(),
            "rect": (r.x(), r.y(), r.width(), r.height()),
            "rotation": item.rotation(),
            "page_index": item.page_index,
            "pos": (item.pos().x(), item.pos().y()),
            "style_color": item._style.color.name(),
            "font_family": item._style.font_family,
            "font_size": item._style.font_size,
        }

    @classmethod
    def _deserialize_stroke(cls, d: dict, page_idx: int) -> StrokeItem:
        path = QPainterPath()
        pts = d.get("points", [])
        if pts:
            path.moveTo(pts[0][0], pts[0][1])
            for px, py in pts[1:]:
                path.lineTo(px, py)
        style = ToolStyle(
            color=QColor(d["color"]),
            width=d["width"],
        )
        item = StrokeItem(
            path=path,
            style=style,
            page_index=d.get("page_index", page_idx),
        )
        if "pos" in d:
            item.setPos(QPointF(*d["pos"]))
        return item

    @classmethod
    def _deserialize_highlight(cls, d: dict, page_idx: int) -> HighlightItem:
        path = QPainterPath()
        pts = d.get("points", [])
        if pts:
            path.moveTo(pts[0][0], pts[0][1])
            for px, py in pts[1:]:
                path.lineTo(px, py)
        style = ToolStyle(
            color=QColor(d["color"]),
            width=d["width"],
        )
        item = HighlightItem(
            style=style,
            page_index=d.get("page_index", page_idx),
        )
        item._path = path
        if "pos" in d:
            item.setPos(QPointF(*d["pos"]))
        return item

    @classmethod
    def _deserialize_textbox(cls, d: dict, page_idx: int) -> TextBoxItem:
        rx, ry, rw, rh = d["rect"]
        style = ToolStyle(
            color=QColor(d.get("style_color", "#000000")),
            font_family=d.get("font_family", "Segoe UI"),
            font_size=d.get("font_size", 14),
        )
        item = TextBoxItem(
            rect=QRectF(rx, ry, rw, rh),
            style=style,
            page_index=d.get("page_index", page_idx),
        )
        item._document.setHtml(d["html"])
        item.setRotation(d.get("rotation", 0.0))
        return item
