"""Double-click launcher (runs without a console window). Same as: pythonw src/main.py [file.pdf]"""
import os
import runpy
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "src"))
sys.argv[0] = os.path.join(here, "src", "main.py")
runpy.run_path(sys.argv[0], run_name="__main__")
