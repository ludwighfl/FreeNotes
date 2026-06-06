import sys
import os
from pathlib import Path

# Add project root to python path
sys.path.append(str(Path(__file__).parent.parent))

if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextDocument, QTextCursor
import fitz

app = QApplication.instance() or QApplication(sys.argv)

doc_qt = QTextDocument()
cursor = QTextCursor(doc_qt)

# Simulating list triggering and arrow triggering
# Trigger bullet list
cursor.insertText("•\u00A0Bullet item\n")
# Trigger dash list (non-breaking hyphen)
cursor.insertText("\u2011\u00A0Dash item\n")
# Trigger arrow
cursor.insertText("Arrow ← here\n")

# Force QTextDocument to calculate its layout
doc_qt.documentLayout().documentSize()

doc_pdf = fitz.open()
page = doc_pdf.new_page()

from core.pdf_text_exporter import PdfTextExporter
from core.pdf_exporter import PdfExporter

block = doc_qt.begin()
while block.isValid():
    block_layout = block.layout()
    if block_layout:
        layout_pos = block_layout.position()
        for line_idx in range(block_layout.lineCount()):
            line = block_layout.lineAt(line_idx)
            line_start = line.textStart()
            line_length = line.textLength()
            it = block.begin()
            while not it.atEnd():
                fragment = it.fragment()
                if fragment.isValid():
                    frag_start = fragment.position() - block.position()
                    frag_end = frag_start + fragment.length()
                    overlap_start = max(frag_start, line_start)
                    overlap_end = min(frag_end, line_start + line_length)
                    if overlap_start < overlap_end:
                        text = fragment.text()[overlap_start - frag_start: overlap_end - frag_start]
                        char_fmt = fragment.charFormat()
                        
                        families = char_fmt.fontFamilies()
                        if isinstance(families, list) and families:
                            family = families[0]
                        elif isinstance(families, str) and families:
                            family = families
                        else:
                            family = doc_qt.defaultFont().family()
                            
                        bold = char_fmt.fontWeight() >= 700
                        italic = char_fmt.fontItalic()
                        
                        font_file = PdfTextExporter._get_system_font_file(family or "arial", bold, italic)
                        fitz_font = PdfTextExporter._map_font(family or "helv", bold, italic)
                        
                        print(f"Text: {repr(text)} | Family: {repr(family)} | FontFile: {font_file} | FitzFont: {fitz_font}")
                it.__next__()
    block = block.next()

doc_pdf.close()
