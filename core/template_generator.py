"""Dynamic PDF template bytes generator for FreeNotes."""

import fitz

def generate_pdf_bytes(template_name: str, orientation: str = "portrait") -> bytes:
    """Generate a template PDF dynamically based on template_name and orientation.
    
    Args:
        template_name: The preset name (e.g. 'kariert.pdf', 'liniert.pdf', 'leer.pdf')
        orientation: 'portrait' or 'landscape'
        
    Returns:
        The generated PDF as bytes.
    """
    doc = fitz.open()
    
    if orientation == "landscape":
        width, height = 841.89, 595.28
    else:
        width, height = 595.28, 841.89
        
    page = doc.new_page(width=width, height=height)
    
    # Strip extension to make matching robust
    name = template_name.lower()
    if name.endswith(".pdf"):
        name = name[:-4]
        
    if name == "liniert":
        # Ruled lines
        # In portrait: y_start=28, spacing=22.5, 36 lines (starts at 28, goes to 28 + 35*22.5 = 815.5)
        # In landscape: y_start=28, spacing=22.5. Let's draw horizontal lines down to height - 20
        y_start = 28.0
        spacing = 22.5
        color = (0.87, 0.87, 0.87)
        stroke_width = 0.5
        
        y = y_start
        while y <= height - 20.0:
            page.draw_line(fitz.Point(0.0, y), fitz.Point(width, y), color=color, width=stroke_width)
            y += spacing
            
    elif name == "kariert":
        # Checkered grid
        # Spacing=17.2, color=(0.92, 0.92, 0.92)
        spacing = 17.2
        color = (0.92, 0.92, 0.92)
        stroke_width = 0.5
        
        # Vertical lines
        x = spacing
        while x < width:
            page.draw_line(fitz.Point(x, 0.0), fitz.Point(x, height), color=color, width=stroke_width)
            x += spacing
            
        # Horizontal lines
        y = spacing
        while y < height:
            page.draw_line(fitz.Point(0.0, y), fitz.Point(width, y), color=color, width=stroke_width)
            y += spacing
            
    pdf_bytes = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return pdf_bytes
