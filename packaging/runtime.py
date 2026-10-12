"""Load Qt's current C++ runtime before another bundled package selects an older one.

PyWinRT ships an older msvcp140.dll. Windows resolves a DLL basename process-wide;
preloading Qt's backward-compatible runtime prevents missing Qt entry points.
This runs only inside PyInstaller, before the Qt runtime hook and application imports.
"""
import ctypes
import os
import sys
from pathlib import Path

if sys.platform == 'win32' and hasattr(sys, '_MEIPASS'):
    qt_dir = Path(sys._MEIPASS) / 'PySide6'
    # Retain both directory and library handles for the process lifetime.
    _qt_runtime_directory = os.add_dll_directory(str(qt_dir))
    _qt_runtime_libraries = []
    for filename in ('VCRUNTIME140.dll', 'VCRUNTIME140_1.dll', 'MSVCP140.dll',
                     'MSVCP140_1.dll', 'MSVCP140_2.dll'):
        library = qt_dir / filename
        if library.is_file():
            _qt_runtime_libraries.append(ctypes.WinDLL(str(library)))
