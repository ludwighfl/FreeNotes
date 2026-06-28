"""Library manager – filesystem operations for the annotation library."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


class LibraryManager:
    """Manages the annotations folder structure on disk.

    A document is a .pdf file optionally paired with a same-named .freenotes
    file. Folders can be nested arbitrarily.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    # Folder operations
    # ------------------------------------------------------------------

    def get_folders(self, parent: Path | None = None) -> list[Path]:
        """Return direct sub-folders of *parent* (default: root)."""
        base = parent or self._root
        if not base.exists():
            return []
        return sorted(p for p in base.iterdir() if p.is_dir()
                       and not p.name.startswith("_"))

    def get_all_folders(self, parent: Path | None = None) -> list[Path]:
        """Return all folders recursively (for sidebar tree)."""
        base = parent or self._root
        return sorted(p for p in base.rglob("*")
                       if p.is_dir() and not p.name.startswith("_"))

    def create_folder(
        self, name: str, parent: Path | None = None
    ) -> Path:
        """Create a new sub-folder and return its path."""
        base = parent or self._root
        folder = base / self._sanitize(name)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def rename_folder(self, folder: Path, new_name: str) -> Path:
        """Rename a folder and return the new path."""
        new_path = folder.parent / self._sanitize(new_name)
        folder.rename(new_path)
        return new_path

    def delete_folder(self, folder: Path, trash: bool = True) -> None:
        """Delete a folder (move to trash by default)."""
        if trash:
            self._move_to_trash(folder)
        else:
            shutil.rmtree(folder)

    # ------------------------------------------------------------------
    # Document operations
    # ------------------------------------------------------------------

    def get_documents(self, folder: Path | None = None) -> list[dict]:
        """Return all documents in *folder* (default: root).

        Each document is a dict with keys:
            pdf, freenotes, name, modified, folder
        """
        base = folder or self._root
        if not base.exists():
            return []

        pdf_files = {p.stem: p for p in base.glob("*.pdf")}
        fn_files = {p.stem: p for p in base.glob("*.freenotes")}

        all_stems = sorted(set(pdf_files) | set(fn_files))
        docs = []

        try:
            from PySide6.QtWidgets import QApplication
            has_qapp = True
        except ImportError:
            has_qapp = False

        for i, stem in enumerate(all_stems):
            if has_qapp and i % 5 == 0:
                QApplication.processEvents()

            pdf = pdf_files.get(stem)
            fn = fn_files.get(stem)
            ref = fn or pdf
            mtime = ref.stat().st_mtime if ref else 0.0
            docs.append({
                "pdf": pdf,
                "freenotes": fn,
                "name": stem,
                "modified": mtime,
                "folder": base,
            })
        return docs

    def get_documents_recursive(
        self, folder: Path | None = None
    ) -> list[dict]:
        """Return all documents in *folder* and all sub-folders recursively."""
        base = folder or self._root
        result: list[dict] = []
        result.extend(self.get_documents(base))
        for subfolder in self.get_folders(base):
            result.extend(self.get_documents_recursive(subfolder))
        return result

    def import_pdf(
        self, source_pdf: Path, target_folder: Path | None = None
    ) -> dict:
        """Import a PDF into the library (copy + create .freenotes).

        Returns the document dict for the imported file.
        """
        dest_folder = target_folder or self._root
        dest_folder.mkdir(parents=True, exist_ok=True)
        dest_pdf = self._resolve_name_conflict(dest_folder / source_pdf.name)
        shutil.copy2(source_pdf, dest_pdf)

        fn_path = dest_pdf.with_suffix(".freenotes")
        self._create_empty_freenotes(fn_path, dest_pdf)

        # Return the matching document dict
        for doc in self.get_documents(dest_folder):
            if doc["pdf"] == dest_pdf:
                return doc
        # Fallback
        return {
            "pdf": dest_pdf,
            "freenotes": fn_path,
            "name": dest_pdf.stem,
            "modified": dest_pdf.stat().st_mtime,
            "folder": dest_folder,
        }

    def create_note_from_preset(self, name: str, preset_pdf_path: Path, target_folder: Path | None = None, orientation: str = "portrait") -> dict:
        """Create a new note from a preset PDF.
        
        Args:
            name: The desired name for the note.
            preset_pdf_path: Path to the preset PDF file.
            target_folder: Folder to place the new note in (defaults to root).
            orientation: "portrait" or "landscape"
            
        Returns:
            The document dictionary of the new note.
        """
        dest_folder = target_folder or self._root
        dest_folder.mkdir(parents=True, exist_ok=True)
        
        safe_name = self._sanitize(name)
        if not safe_name:
            safe_name = "Neue Notiz"
            
        base_path = dest_folder / safe_name
        dest_pdf = self._resolve_name_conflict(base_path.with_suffix(".pdf"))
        
        # Generate landscape dynamically or copy preset PDF to the destination
        if orientation == "landscape":
            from core.template_generator import generate_pdf_bytes
            pdf_bytes = generate_pdf_bytes(preset_pdf_path.name, "landscape")
            dest_pdf.write_bytes(pdf_bytes)
        else:
            shutil.copy2(preset_pdf_path, dest_pdf)
        
        # Create empty .freenotes
        fn_path = dest_pdf.with_suffix(".freenotes")
        self._create_empty_freenotes(fn_path, dest_pdf, template_name=preset_pdf_path.name, orientation=orientation)
        
        # Return the new document dict
        for doc in self.get_documents(dest_folder):
            if doc["pdf"] == dest_pdf:
                return doc
                
        # Fallback
        return {
            "pdf": dest_pdf,
            "freenotes": fn_path,
            "name": dest_pdf.stem,
            "modified": dest_pdf.stat().st_mtime,
            "folder": dest_folder,
        }

    def rename_document(self, doc: dict, new_name: str) -> dict:
        """Rename both .pdf and .freenotes files."""
        safe_name = self._sanitize(new_name)
        folder = doc["folder"]
        new_pdf = None
        if doc["pdf"]:
            new_pdf = folder / f"{safe_name}.pdf"
            doc["pdf"].rename(new_pdf)
        if doc["freenotes"]:
            new_fn = folder / f"{safe_name}.freenotes"
            if new_pdf:
                self._update_freenotes_pdf_path(doc["freenotes"], new_pdf)
            doc["freenotes"].rename(new_fn)
        # Return fresh dict
        for d in self.get_documents(folder):
            if d["name"] == safe_name:
                return d
        return doc

    def delete_document(self, doc: dict, trash: bool = True) -> None:
        """Delete a document's files."""
        for key in ("pdf", "freenotes"):
            path = doc.get(key)
            if path and path.exists():
                if trash:
                    self._move_to_trash(path)
                else:
                    path.unlink(missing_ok=True)

    def duplicate_document(self, doc: dict) -> dict:
        """Duplicate a document (both pdf and freenotes if they exist)."""
        folder = doc["folder"]
        
        # Determine base path for the duplicate
        base_path = folder / doc["name"]
        dup_pdf = self._resolve_name_conflict(base_path.with_suffix(".pdf"))
        new_name = dup_pdf.stem
        
        dup_fn = folder / f"{new_name}.freenotes"
        
        # Copy files
        if doc.get("pdf") and doc["pdf"].exists():
            shutil.copy2(doc["pdf"], dup_pdf)
            
        if doc.get("freenotes") and doc["freenotes"].exists():
            shutil.copy2(doc["freenotes"], dup_fn)
            # Update internal PDF path reference if PDF was copied
            if doc.get("pdf"):
                self._update_freenotes_pdf_path(dup_fn, dup_pdf)
                
        # Return new doc
        for d in self.get_documents(folder):
            if d["name"] == new_name:
                return d
        
        return {
            "pdf": dup_pdf if (doc.get("pdf") and doc["pdf"].exists()) else None,
            "freenotes": dup_fn if (doc.get("freenotes") and doc["freenotes"].exists()) else None,
            "name": new_name,
            "modified": dup_pdf.stat().st_mtime if dup_pdf.exists() else 0.0,
            "folder": folder
        }

    def merge_documents(self, docs: list[dict], new_name: str, folder: Path) -> dict:
        """Merge multiple documents (PDFs and annotations) into a new document in the specified folder.

        Args:
            docs: List of document dicts in the desired order.
            new_name: The name of the merged document.
            folder: The destination folder.

        Returns:
            The document dict of the merged file.
        """
        import fitz
        
        safe_name = self._sanitize(new_name)
        if not safe_name:
            safe_name = "Zusammengeführt"
            
        dest_pdf = self._resolve_name_conflict(folder / f"{safe_name}.pdf")
        merged_name = dest_pdf.stem
        dest_fn = folder / f"{merged_name}.freenotes"
        
        # First, collect all page heights in logical coordinates (points * scale)
        # for all source documents in their virtual order, so we can calculate
        # both source and merged page Y-offsets.
        source_y_offsets = {}  # doc_idx -> list of Y-offsets for its virtual pages
        all_heights_logical = []
        
        for doc_idx, doc in enumerate(docs):
            pdf_path = doc.get("pdf")
            if not pdf_path or not pdf_path.exists():
                continue
            
            doc_pdf = fitz.open(str(pdf_path))
            old_count = doc_pdf.page_count
            
            page_map = []
            fn_path = doc.get("freenotes")
            if fn_path and fn_path.exists():
                try:
                    with open(fn_path, "r", encoding="utf-8") as f:
                        fn_data = json.load(f)
                    page_map = fn_data.get("page_map", [])
                except Exception:
                    pass
            
            offsets = []
            y_offset = 20.0  # PAGE_GAP
            scale = 150.0 / 72.0
            
            if page_map:
                for orig_idx in page_map:
                    offsets.append(y_offset)
                    if orig_idx == -1:
                        h_pt = 842.0
                        if old_count > 0:
                            h_pt = doc_pdf[0].rect.height
                    elif 0 <= orig_idx < old_count:
                        h_pt = doc_pdf[orig_idx].rect.height
                    else:
                        h_pt = 842.0
                    h_logical = h_pt * scale
                    all_heights_logical.append(h_logical)
                    y_offset += h_logical + 20.0
            else:
                for p in range(old_count):
                    offsets.append(y_offset)
                    h_pt = doc_pdf[p].rect.height
                    h_logical = h_pt * scale
                    all_heights_logical.append(h_logical)
                    y_offset += h_logical + 20.0
            
            source_y_offsets[doc_idx] = offsets
            doc_pdf.close()

        # Calculate merged document page Y-offsets
        merged_y_offsets = []
        y_offset = 20.0
        for h_logical in all_heights_logical:
            merged_y_offsets.append(y_offset)
            y_offset += h_logical + 20.0
            
        merged_pdf = fitz.open()
        current_page_offset = 0
        merged_pages_data = {}
        
        for doc_idx, doc in enumerate(docs):
            pdf_path = doc.get("pdf")
            if not pdf_path or not pdf_path.exists():
                continue
            
            doc_pdf = fitz.open(str(pdf_path))
            old_count = doc_pdf.page_count
            
            page_map = []
            pages_data = {}
            fn_path = doc.get("freenotes")
            if fn_path and fn_path.exists():
                try:
                    with open(fn_path, "r", encoding="utf-8") as f:
                        fn_data = json.load(f)
                    page_map = fn_data.get("page_map", [])
                    pages_data = fn_data.get("pages", {})
                except Exception as e:
                    print(f"Failed to read freenotes of {pdf_path.name}: {e}")
            
            # 1. Merge PDF pages
            if page_map:
                for orig_idx in page_map:
                    if orig_idx == -1:
                        w, h = 595, 842
                        if old_count > 0:
                            p0 = doc_pdf[0]
                            w, h = p0.rect.width, p0.rect.height
                        merged_pdf.insert_page(-1, width=w, height=h)
                    elif 0 <= orig_idx < old_count:
                        merged_pdf.insert_pdf(doc_pdf, from_page=orig_idx, to_page=orig_idx)
                    else:
                        merged_pdf.insert_page(-1, width=595, height=842)
                effective_page_count = len(page_map)
            else:
                merged_pdf.insert_pdf(doc_pdf)
                effective_page_count = old_count

            doc_pdf.close()
            
            # 2. Shift and merge annotation page numbers & coordinates
            if pages_data:
                for page_str, page_data in pages_data.items():
                    try:
                        old_page_idx = int(page_str)
                        new_page_idx = current_page_offset + old_page_idx
                        
                        # Calculate Y-offset shift
                        shift_y = 0.0
                        if doc_idx in source_y_offsets and old_page_idx < len(source_y_offsets[doc_idx]):
                            orig_y = source_y_offsets[doc_idx][old_page_idx]
                            new_y = merged_y_offsets[new_page_idx]
                            shift_y = new_y - orig_y
                        
                        adjusted_page_data = {
                            "strokes": [],
                            "highlights": [],
                            "textboxes": [],
                            "shapes": [],
                            "images": [],
                        }
                        
                        for stroke in page_data.get("strokes", []):
                            s_copy = dict(stroke)
                            s_copy["page_index"] = new_page_idx
                            if "pos" in s_copy:
                                px, py = s_copy["pos"]
                                s_copy["pos"] = (px, py + shift_y)
                            adjusted_page_data["strokes"].append(s_copy)
                            
                        for hl in page_data.get("highlights", []):
                            hl_copy = dict(hl)
                            hl_copy["page_index"] = new_page_idx
                            if "pos" in hl_copy:
                                px, py = hl_copy["pos"]
                                hl_copy["pos"] = (px, py + shift_y)
                            adjusted_page_data["highlights"].append(hl_copy)
                            
                        for tb in page_data.get("textboxes", []):
                            tb_copy = dict(tb)
                            tb_copy["page_index"] = new_page_idx
                            if "pos" in tb_copy:
                                px, py = tb_copy["pos"]
                                tb_copy["pos"] = (px, py + shift_y)
                            if "rect" in tb_copy:
                                rx, ry, rw, rh = tb_copy["rect"]
                                tb_copy["rect"] = (rx, ry + shift_y, rw, rh)
                            adjusted_page_data["textboxes"].append(tb_copy)
                            
                        for sh in page_data.get("shapes", []):
                            sh_copy = dict(sh)
                            sh_copy["page_index"] = new_page_idx
                            if "pos" in sh_copy:
                                px, py = sh_copy["pos"]
                                sh_copy["pos"] = (px, py + shift_y)
                            if "rect" in sh_copy:
                                rx, ry, rw, rh = sh_copy["rect"]
                                sh_copy["rect"] = (rx, ry + shift_y, rw, rh)
                            adjusted_page_data["shapes"].append(sh_copy)
                            
                        for img in page_data.get("images", []):
                            img_copy = dict(img)
                            img_copy["page_index"] = new_page_idx
                            if "pos" in img_copy:
                                px, py = img_copy["pos"]
                                img_copy["pos"] = (px, py + shift_y)
                            if "rect" in img_copy:
                                rx, ry, rw, rh = img_copy["rect"]
                                img_copy["rect"] = (rx, ry + shift_y, rw, rh)
                            adjusted_page_data["images"].append(img_copy)
                            
                        # If page has any annotations, add it
                        if any(adjusted_page_data.values()):
                            merged_pages_data[str(new_page_idx)] = adjusted_page_data
                    except Exception as e:
                        print(f"Failed to shift page {page_str} annotations: {e}")
                        
            current_page_offset += effective_page_count
            
        # Save merged PDF
        merged_pdf.save(str(dest_pdf), garbage=3, deflate=True)
        merged_pdf.close()
        
        # Save merged freenotes JSON
        freenotes_data = {
            "version": 1,
            "pdf_path": str(dest_pdf),
            "pages": merged_pages_data,
        }
        with open(dest_fn, "w", encoding="utf-8") as f:
            json.dump(freenotes_data, f, indent=2, ensure_ascii=False)
            
        # Return new doc dict
        for d in self.get_documents(folder):
            if d["name"] == merged_name:
                return d
                
        return {
            "pdf": dest_pdf,
            "freenotes": dest_fn,
            "name": merged_name,
            "modified": dest_pdf.stat().st_mtime,
            "folder": folder
        }

        
    def move_document(self, doc: dict, target_folder: Path) -> dict:
        """Move a document to a different folder."""
        if not target_folder.exists() or doc["folder"] == target_folder:
            return doc
            
        new_pdf = None
        new_fn = None
        new_name = doc["name"]
        
        if doc.get("pdf") and doc["pdf"].exists():
            dest = self._resolve_name_conflict(target_folder / doc["pdf"].name)
            new_name = dest.stem
            shutil.move(str(doc["pdf"]), str(dest))
            new_pdf = dest
            
        if doc.get("freenotes") and doc["freenotes"].exists():
            dest = target_folder / f"{new_name}.freenotes"
            shutil.move(str(doc["freenotes"]), str(dest))
            new_fn = dest
            if new_pdf:
                self._update_freenotes_pdf_path(new_fn, new_pdf)
                
        for d in self.get_documents(target_folder):
            if d["name"] == new_name:
                return d
                
        return doc

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize(name: str) -> str:
        """Remove characters invalid in file names."""
        return re.sub(r'[<>:"/\\|?*]', "_", name.strip())

    @staticmethod
    def _resolve_name_conflict(path: Path) -> Path:
        """Append _2, _3, … if *path* already exists."""
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        i = 2
        while True:
            candidate = parent / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                return candidate
            i += 1

    @staticmethod
    def _create_empty_freenotes(fn_path: Path, pdf_path: Path, template_name: str | None = None, orientation: str | None = None) -> None:
        """Write a minimal .freenotes JSON file."""
        data = {
            "version": 1,
            "pdf_path": str(pdf_path),
            "pages": {},
        }
        if template_name:
            data["template_name"] = template_name
        if orientation:
            data["orientation"] = orientation
        fn_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _update_freenotes_pdf_path(fn_path: Path, new_pdf: Path) -> None:
        """Update the pdf_path field inside a .freenotes file."""
        try:
            data = json.loads(fn_path.read_text(encoding="utf-8"))
            data["pdf_path"] = str(new_pdf)
            fn_path.write_text(
                json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"Warning: pdf_path update failed: {e}")

    def _move_to_trash(self, path: Path) -> None:
        """Move *path* to OS trash."""
        import send2trash
        send2trash.send2trash(str(path))
