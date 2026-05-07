import os

class Test:
    def __init__(self):
        self.doc = "open"
    
    def overwrite(self):
        self.doc = "closed"
        import time
        success = False
        last_err = None
        for _ in range(5):
            try:
                # Simulate os.replace raising WinError 5
                raise PermissionError(5, "Zugriff verweigert", "A", 5, "B")
                success = True
                break
            except PermissionError as e:
                last_err = e
                time.sleep(0.01)
        
        if not success:
            self.doc = "reopened"
            if last_err:
                raise last_err
        else:
            self.doc = "reopened"

t = Test()
try:
    t.overwrite()
except Exception as e:
    print("Caught:", repr(e))

print("doc state:", t.doc)
