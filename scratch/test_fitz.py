import fitz
import os

with open("dummy.pdf", "w") as f:
    f.write("hello")

try:
    doc = fitz.open("dummy.pdf")
    print("Opened!", doc.is_closed)
except Exception as e:
    print("Failed to open:", type(e), e)
    
os.remove("dummy.pdf")
