"""ZIP bulk exporter – export entire library as annotated PDFs or backup."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from core.library_manager import LibraryManager


class ZipExporter:
    """Export the entire annotation library to a ZIP archive."""

    def __init__(self, library_manager: LibraryManager) -> None:
        self._lm = library_manager

    # ------------------------------------------------------------------
    # Mode A: annotated PDFs
    # ------------------------------------------------------------------

    def export_annotated_pdfs(
        self,
        target_zip: Path,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> None:
        """Export all documents as annotated PDFs in a ZIP."""
        from core.pdf_exporter import PdfExporter

        docs = self._collect_all_documents()
        total = len(docs)
        if total == 0:
            return

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with zipfile.ZipFile(
                target_zip, "w", zipfile.ZIP_DEFLATED
            ) as zf:
                for i, (doc, rel_folder) in enumerate(docs):
                    if progress_callback:
                        progress_callback(
                            int(i / total * 100), doc["name"])

                    pdf_src = doc.get("pdf")
                    fn_src = doc.get("freenotes")
                    if not pdf_src or not pdf_src.exists():
                        continue

                    out_pdf = tmp_path / f"{doc['name']}.pdf"

                    if fn_src and fn_src.exists():
                        try:
                            scene, dm = self._build_temp_scene(
                                fn_src, pdf_src)
                            exporter = PdfExporter(scene, dm)
                            exporter.export(str(pdf_src), str(out_pdf))
                        except Exception as e:
                            print(
                                f"Export {doc['name']} failed: {e}")
                            shutil.copy2(pdf_src, out_pdf)
                    else:
                        shutil.copy2(pdf_src, out_pdf)

                    arc_name = str(
                        rel_folder / f"{doc['name']}.pdf")
                    zf.write(out_pdf, arc_name)

        if progress_callback:
            progress_callback(100, "Fertig")

    # ------------------------------------------------------------------
    # Mode B: backup
    # ------------------------------------------------------------------

    def export_backup(
        self,
        target_zip: Path,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> None:
        """Export all documents as raw .pdf + .freenotes pairs."""
        docs = self._collect_all_documents()
        total = len(docs) * 2
        done = 0

        with zipfile.ZipFile(
            target_zip, "w", zipfile.ZIP_DEFLATED
        ) as zf:
            for doc, rel_folder in docs:
                for key, suffix in [
                    ("pdf", ".pdf"),
                    ("freenotes", ".freenotes"),
                ]:
                    src = doc.get(key)
                    if src and src.exists():
                        arc = str(
                            rel_folder / f"{doc['name']}{suffix}")
                        zf.write(src, arc)
                    done += 1
                    if progress_callback:
                        progress_callback(
                            int(done / total * 100),
                            doc["name"],
                        )

        if progress_callback:
            progress_callback(100, "Fertig")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _collect_all_documents(
        self,
    ) -> list[tuple[dict, Path]]:
        """Collect all documents from root and sub-folders."""
        result: list[tuple[dict, Path]] = []
        # Root-level
        for doc in self._lm.get_documents(self._lm.root):
            result.append((doc, Path(".")))
        # Sub-folders
        for folder in self._lm.get_all_folders():
            rel = folder.relative_to(self._lm.root)
            for doc in self._lm.get_documents(folder):
                result.append((doc, rel))
        return result

    @staticmethod
    def _build_temp_scene(
        fn_path: Path, pdf_path: Path
    ) -> tuple["PageScene", "DocumentManager"]:
        """Build a minimal PageScene with loaded annotations for export."""
        from core.document_manager import DocumentManager
        from core.freenotes_store import FreenotesStore
        from ui.scene.page_scene import PageScene

        dm = DocumentManager()
        dm.open_document(str(pdf_path))
        scene = PageScene()
        scene.load_document(dm)
        FreenotesStore.load(str(fn_path), scene, dm)
        return scene, dm
