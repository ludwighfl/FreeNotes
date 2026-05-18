import sys
import os
sys.path.append(os.getcwd())

from core.tile_cache import TileCache, TileKey, MipLevel
from PySide6.QtGui import QImage

try:
    cache = TileCache()
    key = TileKey(0, 0, 0, MipLevel.THUMB)
    img = QImage(100, 100, QImage.Format.Format_RGB888)
    cache.put(key, img)
    print("Put successful")
    
    key2 = TileKey(0, 0, 0, MipLevel.FULL)
    cache.put(key2, img)
    print("Put FULL successful")
    
    assert cache.get(key) is not None
    assert cache.get(key2) is not None
    print("Get successful")
    
    print(f"Memory estimate: {cache.estimated_memory_mb()} MB")
    
    cache.invalidate_page(0)
    assert cache.get(key) is None
    print("Invalidate successful")
    
    print("TileCache isolation test PASSED")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
