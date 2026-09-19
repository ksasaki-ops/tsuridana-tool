"""
ユーザー設定 (担当者の選択) の保存・読込

.exe は毎回一時フォルダに展開されるため、設定は %APPDATA% に置く。
"""
import json
import os


def default_settings_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "tsuridana-tool", "settings.json")


def load_settings(path: str | None = None) -> dict:
    """設定を読む。ファイルが無い・壊れている場合は初期値を返す。"""
    settings = {"tantou": "", "tantou_list": []}
    try:
        with open(path or default_settings_path(), encoding="utf-8") as fp:
            data = json.load(fp)
        tantou, tantou_list = data["tantou"], data["tantou_list"]
        if isinstance(tantou, str) and isinstance(tantou_list, list) \
                and all(isinstance(n, str) for n in tantou_list):
            settings = {"tantou": tantou, "tantou_list": tantou_list}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return settings


def save_settings(settings: dict, path: str | None = None):
    path = path or default_settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(settings, fp, ensure_ascii=False, indent=2)


def remember_tantou(settings: dict, name: str) -> dict:
    """担当者を「現在の選択」にし、候補リストの先頭へ (重複なし)。空の名前は無視。"""
    name = name.strip()
    if not name:
        return settings
    others = [n for n in settings["tantou_list"] if n != name]
    return {"tantou": name, "tantou_list": [name] + others}
