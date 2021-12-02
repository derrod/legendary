import os
import sys


def is_pyinstaller():
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def is_windows_or_pyi():
    return is_pyinstaller() or os.name == 'nt'


def is_windows_mac_or_pyi():
    return is_pyinstaller() or os.name == 'nt' or sys.platform == 'darwin'
