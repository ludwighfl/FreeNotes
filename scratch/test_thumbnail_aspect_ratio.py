import sys
import shutil
from pathlib import Path

# Add project root to python path so we can import modules
sys.path.append(str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage
from PySide6.QtCore import QEventLoop

from core.library_manager import LibraryManager
from core.document_manager import DocumentManager
from core.thumbnail_worker import ThumbnailWorker

def run_test():
    # A QApplication is required for signals/slots and QThread
    app = QApplication.instance() or QApplication(sys.argv)

    test_dir = Path("./scratch/test_env_thumb")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir(parents=True, exist_ok=True)

    lm = LibraryManager(test_dir)
    presets_dir = Path("./assets/presets")
    preset_pdf = presets_dir / "kariert.pdf"

    print("1. Creating Checkered Landscape note...")
    doc_dict = lm.create_note_from_preset("TestThumbL", preset_pdf, orientation="landscape")
    pdf_path = doc_dict["pdf"]

    dm = DocumentManager()
    opened = dm.open_document(pdf_path)
    assert opened, "Failed to open document"

    # Insert a new landscape page
    print("2. Inserting a new landscape page...")
    dm.insert_page(at_index=1, reference_idx=0)

    # The mapping should be -1 for the newly inserted page
    orig_idx = dm.page_map[1]
    assert orig_idx == -1, f"Expected mapping to be -1, got {orig_idx}"

    w, h = dm.get_page_size(1)
    print(f"Page 1 size from DocumentManager: {w} x {h}")
    assert w > h, f"Expected landscape width > height, got {w} x {h}"

    # Setup tasks list as it would be constructed in sidebar_render
    tasks = [(1, orig_idx, w, h)]

    print("3. Spawning ThumbnailWorker and waiting for ready signal...")
    worker = ThumbnailWorker(dm, tasks, dpi=72, use_hidpi=False, generation_id=42)

    loop = QEventLoop()
    emitted_images = []

    def on_thumbnail_ready(gen_id, idx, img):
        print(f"Signal received: gen_id={gen_id}, idx={idx}, image_size={img.width()}x{img.height()}")
        emitted_images.append((idx, img))
        loop.quit()

    worker.thumbnail_ready.connect(on_thumbnail_ready)
    worker.start()
    loop.exec()

    # Wait for the thread to completely finish/clean up
    worker.wait()

    assert len(emitted_images) == 1, "Expected exactly 1 thumbnail_ready emission"
    idx, img = emitted_images[0]
    assert idx == 1, f"Expected index 1, got {idx}"
    assert img.width() > img.height(), f"Expected landscape QImage (width > height), got {img.width()}x{img.height()}"
    print(f"Success: Emitted image has correct landscape dimensions: {img.width()}x{img.height()}")

    dm.close_document()
    shutil.rmtree(test_dir)
    print("All thumbnail aspect ratio tests passed successfully!")

if __name__ == "__main__":
    run_test()
