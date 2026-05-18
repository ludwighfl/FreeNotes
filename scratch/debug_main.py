import sys
import traceback
import os

# Add current directory to path
sys.path.append(os.getcwd())

try:
    import main
    print("Main imported, running main.main()...")
    main.main()
except SystemExit as e:
    print(f"SystemExit: {e.code}")
    if e.code != 0:
        traceback.print_exc()
except Exception as e:
    print("Exception occurred:")
    traceback.print_exc()
