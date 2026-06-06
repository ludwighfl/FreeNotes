import fitz
import sys

doc = fitz.open()
page = doc.new_page()

# Let's check if we can find Arial on Windows
font_paths = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
]

import os
for path in font_paths:
    exists = os.path.exists(path)
    print(f"{path} exists: {exists}")

# Try inserting Unicode text with/without fontfile
try:
    page.insert_text(fitz.Point(100, 100), "Sonderzeichen: ← · •", fontname="helv")
    print("Base-14 insertion succeeded (characters might be replaced inside PDF though)")
except Exception as e:
    print("Base-14 error:", e)

# Try inserting with fontfile
for path in font_paths:
    if os.path.exists(path):
        try:
            # When fontfile is provided, fontname becomes a key we assign to it
            page.insert_text(fitz.Point(100, 150), "Sonderzeichen: ← · •", fontname="custom", fontfile=path)
            print(f"Fontfile insertion with {path} succeeded")
            break
        except Exception as e:
            print(f"Fontfile {path} error:", e)

doc.save("scratch/test_unicode_output.pdf")
doc.close()
print("Saved PDF to scratch/test_unicode_output.pdf")
