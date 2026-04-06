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
    def _create_empty_freenotes(fn_path: Path, pdf_path: Path) -> None:
        """Write a minimal .freenotes JSON file."""
        data = {
            "version": 1,
            "pdf_path": str(pdf_path),
            "pages": {},
        }
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
