import sys
import shutil
from pathlib import Path

# Add project root to python path so we can import core modules
sys.path.append(str(Path(__file__).parent.parent))

import fitz
from core.library_manager import LibraryManager
from core.document_manager import DocumentManager
from core.freenotes_store import FreenotesStore
from ui.scene.page_scene import PageScene

def run_test():
    test_dir = Path("./scratch/test_env")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)
    
    lm = LibraryManager(test_dir)
    presets_dir = Path("./assets/presets")
    preset_pdf = presets_dir / "kariert.pdf"
    
    print("Creating Checkered Landscape note...")
    doc_dict = lm.create_note_from_preset("TestKariertL", preset_pdf, orientation="landscape")
    pdf_path = doc_dict["pdf"]
    fn_path = doc_dict["freenotes"]
    
    print(f"Created PDF: {pdf_path}")
    print(f"Created Freenotes: {fn_path}")
    
    # 1. Verify dimensions of note
    doc = fitz.open(str(pdf_path))
    assert doc.page_count == 1, f"Expected 1 page, got {doc.page_count}"
    page0 = doc[0]
    print(f"Page 0 dimensions: {page0.rect.width} x {page0.rect.height}")
    assert abs(page0.rect.width - 841.89) < 0.1, f"Expected width ~841.89, got {page0.rect.width}"
    assert abs(page0.rect.height - 595.28) < 0.1, f"Expected height ~595.28, got {page0.rect.height}"
    
    # Verify drawing count on page 0
    drawings = page0.get_drawings()
    print(f"Page 0 drawings count: {len(drawings)}")
    assert len(drawings) == 82, f"Expected 82 drawings for checkered, got {len(drawings)}"
    doc.close()
    
    # 2. Verify page insertion
    dm = DocumentManager()
    opened = dm.open_document(pdf_path)
    assert opened, "Failed to open document"
    
    # A QApplication is required for PageScene / QGraphicsScene
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    
    scene = PageScene()
    FreenotesStore.load(str(fn_path), scene, dm)
    
    assert dm.template_name == "kariert.pdf", f"Expected template_name 'kariert.pdf', got {dm.template_name}"
    assert dm.orientation == "landscape", f"Expected orientation 'landscape', got {dm.orientation}"
    
    print("Inserting a new page...")
    dm.insert_page(at_index=1, reference_idx=0)
    
    # Save document changes
    dm.overwrite_pdf()
    dm.close_document()
    
    # Reopen and check the inserted page
    doc2 = fitz.open(str(pdf_path))
    assert doc2.page_count == 2, f"Expected 2 pages after insertion, got {doc2.page_count}"
    page1 = doc2[1]
    print(f"Page 1 dimensions: {page1.rect.width} x {page1.rect.height}")
    assert abs(page1.rect.width - 841.89) < 0.1, f"Expected page 1 width ~841.89, got {page1.rect.width}"
    assert abs(page1.rect.height - 595.28) < 0.1, f"Expected page 1 height ~595.28, got {page1.rect.height}"
    
    drawings1 = page1.get_drawings()
    print(f"Page 1 drawings count: {len(drawings1)}")
    assert len(drawings1) == 82, f"Expected 82 drawings for page 1 checkered, got {len(drawings1)}"
    doc2.close()
    
    # Clean up test folder
    shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)

    preset_pdf_ruled = presets_dir / "liniert.pdf"
    
    print("Creating Ruled Landscape note...")
    doc_dict_ruled = lm.create_note_from_preset("TestLiniertL", preset_pdf_ruled, orientation="landscape")
    pdf_path_ruled = doc_dict_ruled["pdf"]
    fn_path_ruled = doc_dict_ruled["freenotes"]
    
    # Verify dimensions and drawings
    doc_ruled = fitz.open(str(pdf_path_ruled))
    page0_ruled = doc_ruled[0]
    print(f"Ruled Page 0 dimensions: {page0_ruled.rect.width} x {page0_ruled.rect.height}")
    assert abs(page0_ruled.rect.width - 841.89) < 0.1
    assert abs(page0_ruled.rect.height - 595.28) < 0.1
    drawings_ruled = page0_ruled.get_drawings()
    print(f"Ruled Page 0 drawings count: {len(drawings_ruled)}")
    assert len(drawings_ruled) == 25, f"Expected 25 drawings for ruled landscape, got {len(drawings_ruled)}"
    doc_ruled.close()
    
    # Verify page insertion
    dm_ruled = DocumentManager()
    dm_ruled.open_document(pdf_path_ruled)
    scene_ruled = PageScene()
    FreenotesStore.load(str(fn_path_ruled), scene_ruled, dm_ruled)
    
    assert dm_ruled.template_name == "liniert.pdf"
    assert dm_ruled.orientation == "landscape"
    
    print("Inserting a new ruled landscape page...")
    dm_ruled.insert_page(at_index=1, reference_idx=0)
    dm_ruled.overwrite_pdf()
    dm_ruled.close_document()
    
    doc2_ruled = fitz.open(str(pdf_path_ruled))
    assert doc2_ruled.page_count == 2
    page1_ruled = doc2_ruled[1]
    assert abs(page1_ruled.rect.width - 841.89) < 0.1
    assert abs(page1_ruled.rect.height - 595.28) < 0.1
    drawings1_ruled = page1_ruled.get_drawings()
    print(f"Ruled Page 1 drawings count: {len(drawings1_ruled)}")
    assert len(drawings1_ruled) == 25, f"Expected 25 drawings for page 1 ruled landscape, got {len(drawings1_ruled)}"
    doc2_ruled.close()

    print("All landscape creation and page insertion tests passed successfully!")
    
    # Clean up test folder
    shutil.rmtree(test_dir)

if __name__ == "__main__":
    run_test()
