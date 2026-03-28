import os
import subprocess
from pathlib import Path
import re

groups = {
    'windows': [
        'main_window.py',
        'viewer_window.py',
        'viewer_file_io.py',
        'viewer_tool_manager.py',
        'manager_view.py',
        'settings_view.py',
        'settings_pages',
        'splash_screen.py',
    ],
    'scene': [
        'page_view.py',
        'page_scene.py',
        'scene_registry.py',
        'scene_clipboard.py',
        'scene_page_manager.py',
        'scene_selection.py',
    ],
    'bars': [
        'toolbar_widget.py',
        'toolbar_icons.py',
        'toolbar_mode_popups.py',
        'formatting_bar.py',
        'search_bar.py',
        'sidebar_widget.py',
    ],
    'components': [
        'icon_factory.py',
        'pdf_card.py',
        'sidebar_item.py',
    ],
    'popups': [
        'color_picker_popup.py',
        'color_wheel_widget.py',
        'font_size_widget.py',
        'textbox_options_popup.py',
        'three_dot_menu.py',
    ]
}

os.chdir(r"C:\Users\ludwi\.gemini\antigravity\scratch\pdf_annotator")
ui_dir = Path("ui")

# 1. Create subdirs
for group in groups:
    (ui_dir / group).mkdir(exist_ok=True)

# 2. Build import renaming map
import_map = {}
for group, files in groups.items():
    for f in files:
        name = f.replace('.py', '')
        old_import = f"ui.{name}"
        new_import = f"ui.{group}.{name}"
        import_map[old_import] = new_import
        
        # Git Move
        src = ui_dir / f
        dest = ui_dir / group / f
        if src.exists():
            print(f"git mv {src} -> {dest}")
            subprocess.run(['git', 'mv', str(src), str(dest)], shell=True)
        else:
            print(f"Skip missing file: {src}")

# Keep track of `zip_export_dialog.py` if it still exists, let's just move it to popups
zip_src = ui_dir / 'zip_export_dialog.py'
if zip_src.exists():
    dest = ui_dir / 'popups' / 'zip_export_dialog.py'
    subprocess.run(['git', 'mv', str(zip_src), str(dest)], shell=True)
    import_map['ui.popups.zip_export_dialog'] = 'ui.popups.zip_export_dialog'

# Additionally, the `ui/` directory might have an `__init__.py` we want to leave alone, 
# and `__pycache__` which we can ignore.

def replace_imports(filepath):
    try:
        content = filepath.read_text(encoding='utf-8')
    except:
        return
        
    new_content = content
    # Sort by length descending to replace longest imports first
    for old, new in sorted(import_map.items(), key=lambda x: len(x[0]), reverse=True):
        pattern = r'\b' + old.replace('.', r'\.') + r'\b'
        new_content = re.sub(pattern, new, new_content)

    if new_content != content:
        print(f"Updated imports in {filepath}")
        filepath.write_text(new_content, encoding='utf-8')

# 3. Apply to all python files
for root, _, files in os.walk("."):
    if ".git" in root or "__pycache__" in root:
        continue
    for f in files:
        if f.endswith(".py"):
            replace_imports(Path(root) / f)

print("Refactoring complete.")
