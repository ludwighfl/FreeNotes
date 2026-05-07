import fitz
import os
import shutil

class DocManager:
    def __init__(self):
        # Create a dummy PDF
        self.path = "dummy.pdf"
        doc = fitz.open()
        doc.insert_page(-1, text="Hello")
        doc.save(self.path)
        doc.close()
        
        self.doc = fitz.open(self.path)

    def overwrite(self):
        temp_path = "dummy.tmp.pdf"
        self.doc.save(temp_path)
        self.doc.close()
        
        # Simulate WinError 5 PermissionError
        success = False
        last_err = PermissionError(5, "Zugriff verweigert", temp_path, 5, self.path)
        
        if not success:
            self.doc = fitz.open(self.path)
            if last_err:
                raise last_err
        else:
            self.doc = fitz.open(self.path)

mgr = DocManager()
print("Page count before:", mgr.doc.page_count)
try:
    mgr.overwrite()
except Exception as e:
    print("Caught Exception:", repr(e))

print("Page count after:", mgr.doc.page_count)
