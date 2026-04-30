"""FreeNotes file store – save/load .freenotes JSON annotation files."""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainterPath, QColor

from core.tool_style import ToolStyle
from items.stroke_item import StrokeItem
from items.highlight_item import HighlightItem
from items.text_box_item import TextBoxItem
from items.shape_item import ShapeItem
from items.image_item import ImageItem

if TYPE_CHECKING:
    from ui.scene.page_scene import PageScene
    from core.document_manager import DocumentManager


class FreenotesStore:
    """Stateless utility class for saving/loading .freenotes files."""

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    @classmethod
    def save(cls, path: str, scene: PageScene, pdf_path: str, doc_manager: DocumentManager) -> None:
        """Save all annotations from *scene* to a .freenotes JSON file."""
        data: dict = {
            "version": 1,
            "pdf_path": pdf_path or "",
            "page_map": getattr(doc_manager, "page_map", []),
            "pages": {},
        }

        # Collect all page indices with annotations
        all_pages: set[int] = set()
        all_pages.update(scene._stroke_items.keys())
        all_pages.update(scene._highlight_items.keys())
        all_pages.update(scene._text_box_items.keys())
        all_pages.update(scene._shape_items.keys())
        all_pages.update(scene._image_items.keys())

        for page_idx in sorted(all_pages):
            page_data: dict = {
                "strokes": [],
                "highlights": [],
                "textboxes": [],
                "shapes": [],
                "images": [],
            }

            for item in scene._stroke_items.get(page_idx, []):
                page_data["strokes"].append(cls._serialize_stroke(item))

            for item in scene._highlight_items.get(page_idx, []):
                page_data["highlights"].append(cls._serialize_highlight(item))

            for item in scene._text_box_items.get(page_idx, []):
                page_data["textboxes"].append(cls._serialize_textbox(item))

            for item in scene._shape_items.get(page_idx, []):
                page_data["shapes"].append(item.to_dict())

            for item in scene._image_items.get(page_idx, []):
                page_data["images"].append(item.to_dict())

            # Skip pages with no annotations
            if any(v for v in page_data.values()):
                data["pages"][str(page_idx)] = page_data

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str, scene: PageScene, doc_manager: DocumentManager) -> tuple[str, bool]:
        """Load annotations from a .freenotes file into *scene*.

        Returns (pdf_path, structural_modified).
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        pdf_path: str = data.get("pdf_path", "")
        page_map: list[int] = data.get("page_map", [])

        structural_modified = False
        if page_map and isinstance(page_map, list) and doc_manager:
            try:
                doc_manager.apply_page_map(page_map)
                scene.rebuild_after_reorder(doc_manager)
                structural_modified = True
            except Exception as e:
                logger.warning("Failed to apply page map: %s", e)

        # Clear existing annotations
        cls._clear_scene_annotations(scene)

        from PySide6.QtWidgets import QGraphicsScene

        # Disable BSP tree during mass insertion for O(1) adds instead of O(log N)
        scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)

        # Suppress scene.changed signals during bulk insertion to prevent
        # O(n²) thumbnail invalidation in the sidebar.
        scene._suppress_scene_changed = True
        try:
            for page_str, page_data in data.get("pages", {}).items():
                page_idx = int(page_str)

                for d in page_data.get("strokes", []):
                    try:
                        item = cls._deserialize_stroke(d, page_idx)
                        scene.addItem(item)
                        scene.add_item_to_registry(item)
                    except Exception as e:
                        logger.warning("Stroke laden fehlgeschlagen: %s", e)

                for d in page_data.get("highlights", []):
                    try:
                        item = cls._deserialize_highlight(d, page_idx)
                        scene.addItem(item)
                        scene.add_item_to_registry(item)
                    except Exception as e:
                        logger.warning("Highlight laden fehlgeschlagen: %s", e)

                for d in page_data.get("textboxes", []):
                    try:
                        item = cls._deserialize_textbox(d, page_idx)
                        scene.addItem(item)
                        scene.add_item_to_registry(item)
                    except Exception as e:
                        logger.warning("Textbox laden fehlgeschlagen: %s", e)

                for d in page_data.get("shapes", []):
                    try:
                        item = ShapeItem.from_dict(d)
                        scene.addItem(item)
                        scene.add_item_to_registry(item)
                    except Exception as e:
                        logger.warning("Shape laden fehlgeschlagen: %s", e)

                for d in page_data.get("images", []):
                    try:
                        item = ImageItem.from_dict(d)
                        scene.addItem(item)
                        scene.add_item_to_registry(item)
                    except Exception as e:
                        logger.warning("Image laden fehlgeschlagen: %s", e)

        finally:
            scene._suppress_scene_changed = False
            # Rebuild BSP tree once in bulk at the end for O(log N) runtime performance
            scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)

        return pdf_path, structural_modified

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    @classmethod
    def _clear_scene_annotations(cls, scene: PageScene) -> None:
        """Remove all annotation items from the scene.

        Iterates over the registry dicts directly instead of
        scene.items() (which is O(n) over ALL scene items including
        tile pixmaps when BSP index is disabled).
        """
        registries = [
            scene._stroke_items,
            scene._highlight_items,
            scene._text_box_items,
            scene._shape_items,
            scene._image_items,
        ]
        for registry in registries:
            for page_items in registry.values():
                for item in page_items:
                    scene.removeItem(item)
            registry.clear()

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
    def serialize_path(cls, path: QPainterPath) -> str:
        from PySide6.QtCore import QByteArray, QDataStream, QIODevice
        ba = QByteArray()
        stream = QDataStream(ba, QIODevice.OpenModeFlag.WriteOnly)
        stream << path
        return ba.toBase64().data().decode("ascii")

    @classmethod
    def deserialize_path(cls, b64_str: str) -> QPainterPath:
        from PySide6.QtCore import QByteArray, QDataStream, QIODevice
        ba = QByteArray.fromBase64(b64_str.encode("ascii"))
        stream = QDataStream(ba, QIODevice.OpenModeFlag.ReadOnly)
        path = QPainterPath()
        stream >> path
        return path

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
            "path_b64": cls.serialize_path(path),
            "color": item._style.color.name(),
            "width": item._style.width,
            "page_index": item.page_index,
            "pos": (item.pos().x(), item.pos().y()),
            "outline_mode": getattr(item, "_outline_mode", False),
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
            "path_b64": cls.serialize_path(path),
            "color": item._style.color.name(),
            "width": item._style.width,
            "page_index": item.page_index,
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
        if "path_b64" in d:
            path = cls.deserialize_path(d["path_b64"])
        else:
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
        item._outline_mode = d.get("outline_mode", False)
        if "pos" in d:
            item.setPos(QPointF(*d["pos"]))
        return item

    @classmethod
    def _deserialize_highlight(cls, d: dict, page_idx: int) -> HighlightItem:
        if "path_b64" in d:
            path = cls.deserialize_path(d["path_b64"])
        else:
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

    # ------------------------------------------------------------------
    # Page-level serialization (for page clipboard)
    # ------------------------------------------------------------------

    @classmethod
    def serialize_page_annotations(cls, scene: "PageScene", page_idx: int) -> dict:
        """Serialize all annotations on *page_idx* to a plain dict.

        The returned dict has the same structure as a single page entry in
        the .freenotes JSON format and can be stored in
        ``AppState.page_clipboard['annotations']``.
        """
        page_data: dict = {
            "strokes": [],
            "highlights": [],
            "textboxes": [],
            "shapes": [],
            "images": [],
        }

        for item in scene._stroke_items.get(page_idx, []):
            page_data["strokes"].append(cls._serialize_stroke(item))

        for item in scene._highlight_items.get(page_idx, []):
            page_data["highlights"].append(cls._serialize_highlight(item))

        for item in scene._text_box_items.get(page_idx, []):
            page_data["textboxes"].append(cls._serialize_textbox(item))

        for item in scene._shape_items.get(page_idx, []):
            page_data["shapes"].append(item.to_dict())

        for item in scene._image_items.get(page_idx, []):
            page_data["images"].append(item.to_dict())

        return page_data

    @classmethod
    def deserialize_page_annotations(
        cls,
        scene: "PageScene",
        page_idx: int,
        page_data: dict,
        pos_offset: tuple[float, float] | None = None,
    ) -> None:
        """Deserialize annotations from *page_data* and add them to *scene*.

        This is the inverse of :meth:`serialize_page_annotations`.  Items
        are added to the scene's registries under *page_idx*.

        Args:
            pos_offset: Optional (dx, dy) offset to apply to every item's
                position.  Used when pasting a page whose annotations
                were serialized at a different scene Y-offset.
        """
        dx, dy = pos_offset if pos_offset else (0.0, 0.0)

        for d in page_data.get("strokes", []):
            try:
                item = cls._deserialize_stroke(d, page_idx)
                item._page_index = page_idx
                if pos_offset:
                    item.setPos(item.pos().x() + dx, item.pos().y() + dy)
                scene.addItem(item)
                scene.add_item_to_registry(item)
            except Exception as e:
                logger.warning("Stroke paste failed: %s", e)

        for d in page_data.get("highlights", []):
            try:
                item = cls._deserialize_highlight(d, page_idx)
                item._page_index = page_idx
                if pos_offset:
                    item.setPos(item.pos().x() + dx, item.pos().y() + dy)
                scene.addItem(item)
                scene.add_item_to_registry(item)
            except Exception as e:
                logger.warning("Highlight paste failed: %s", e)

        for d in page_data.get("textboxes", []):
            try:
                item = cls._deserialize_textbox(d, page_idx)
                item._page_index = page_idx
                if pos_offset:
                    item.setPos(item.pos().x() + dx, item.pos().y() + dy)
                scene.addItem(item)
                scene.add_item_to_registry(item)
            except Exception as e:
                logger.warning("Textbox paste failed: %s", e)

        for d in page_data.get("shapes", []):
            try:
                item = ShapeItem.from_dict(d)
                item._page_index = page_idx
                if pos_offset:
                    item.setPos(item.pos().x() + dx, item.pos().y() + dy)
                scene.addItem(item)
                scene.add_item_to_registry(item)
            except Exception as e:
                logger.warning("Shape paste failed: %s", e)

        for d in page_data.get("images", []):
            try:
                item = ImageItem.from_dict(d)
                item._page_index = page_idx
                if pos_offset:
                    item.setPos(item.pos().x() + dx, item.pos().y() + dy)
                scene.addItem(item)
                scene.add_item_to_registry(item)
            except Exception as e:
                logger.warning("Image paste failed: %s", e)
