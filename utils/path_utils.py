"""
.exe / 開発環境どちらでも動くパス解決ユーティリティ
"""
import sys
import os


def get_base_dir() -> str:
    """PyInstaller の _MEIPASS（解凍先）か、スクリプトのディレクトリを返す"""
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def asset(filename: str) -> str:
    """assets/ フォルダ内のファイルパスを返す"""
    return os.path.join(get_base_dir(), "assets", filename)


def coordinates_path() -> str:
    """coordinates.json のパスを返す"""
    return os.path.join(get_base_dir(), "coordinates.json")


def downloads_dir() -> str:
    """ユーザーの Downloads フォルダパスを返す"""
    return os.path.join(os.path.expanduser("~"), "Downloads")
