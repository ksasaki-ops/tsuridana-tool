"""
洗濯機上吊戸棚 発注ツール - メインエントリポイント
"""
import sys
import os

# PyInstaller --windowed では stdout/stderr が None になるため補完
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import tkinter as tk

# PyInstaller でパスが変わっても動くように sys.path を調整
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.main_window import MainWindow


def main():
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
