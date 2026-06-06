import fitz
import os

doc = fitz.open()
page = doc.new_page()

sys_root = os.environ.get("SystemRoot", "C:\\Windows")
arial_path = os.path.join(sys_root, "Fonts", "arial.ttf")

print("Arial Path:", arial_path, "Exists:", os.path.exists(arial_path))

# Insert text with fontfile
page.insert_text(
    point=fitz.Point(50, 100),
    text="Bullet: •, Arrow: ←, Em-dash: —, Umlaut: äöüß",
    fontsize=14,
    fontname="custom-arial",
    fontfile=arial_path
)

doc.save("scratch/test_unicode_export_output.pdf")
doc.close()

# Reopen and check drawings or extract text
doc2 = fitz.open("scratch/test_unicode_export_output.pdf")
text = doc2[0].get_text()
print("Extracted Text:")
print(repr(text))
doc2.close()
