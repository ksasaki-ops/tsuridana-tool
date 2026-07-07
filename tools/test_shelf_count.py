"""
棚板枚数機能テスト

使い方:
    py -3 tools/test_shelf_count.py
"""
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.argv[0] = os.path.join(ROOT, "tsuridana.py")

from core.text_builder import OrderSpec, build_spec_lines


def _spec(**kw):
    base = dict(
        customer="テスト", property_name="",
        W=760, D=450, H=600,
        men_zai_ari=False, tobira_hinban="",
        body_material="白ポリ", filler="両側",
        hg=False, tobira_enchou=False, kirikake=False,
    )
    base.update(kw)
    return OrderSpec(**base)


# === テスト1: tana_count 既定値=1、仕様テキスト ===
print("=== テスト1: tana_count 既定 & テキスト ===")
spec_default = _spec()
assert spec_default.tana_count == 1, f"FAIL: 既定 tana_count は 1: {spec_default.tana_count}"
lines = build_spec_lines(spec_default)
assert "棚板1枚ダボ可動式" in lines, f"FAIL: 既定テキスト不一致: {lines}"
print("  OK: 既定 tana_count=1 / 「棚板1枚ダボ可動式」")

for n in (2, 3, 4):
    lines_n = build_spec_lines(_spec(tana_count=n))
    assert f"棚板{n}枚ダボ可動式" in lines_n, f"FAIL: N={n} テキスト不一致: {lines_n}"
    print(f"  OK: N={n} → 「棚板{n}枚ダボ可動式」")

# === テスト2: _path_end_point ===
print("=== テスト2: _path_end_point ===")
from core.svg_renderer import _path_end_point

# 絶対M + 相対v/m の連鎖（front shaft 相当）
x, y = _path_end_point("M306.3 190.1v5.3m0 9.2v9.2")
assert abs(x - 306.3) < 1e-6 and abs(y - (190.1 + 5.3 + 9.2 + 9.2)) < 1e-6, f"FAIL: {x},{y}"
print(f"  OK: 縦連鎖 → ({x},{y})")

# 相対 h と絶対 H の混在
x2, y2 = _path_end_point("M10 10h5H100v3")
assert abs(x2 - 100) < 1e-6 and abs(y2 - 13) < 1e-6, f"FAIL: {x2},{y2}"
print(f"  OK: h/H/v → ({x2},{y2})")

# === テスト3: _shelf_targets(絶対内寸モデル) ===
print("=== テスト3: _shelf_targets ===")
from core.svg_renderer import _shelf_targets, _SHELF_CAVITY

# N=3 の中央は内寸中点
top, bottom = _SHELF_CAVITY[("A", "section")]
t3 = _shelf_targets("A", "section", 3)
assert abs(t3[1] - (top + bottom) / 2) < 1e-6, f"FAIL: 中央が中点でない: {t3}"
# 昇順・内寸内
assert t3 == sorted(t3) and top < t3[0] and t3[-1] < bottom, f"FAIL: {t3}"
print(f"  OK: N=3 section → {[round(v,1) for v in t3]}")

t2 = _shelf_targets("A", "front", 2)
assert len(t2) == 2 and t2[0] < t2[1], f"FAIL: {t2}"
print(f"  OK: N=2 front → {[round(v,1) for v in t2]}")

# === テスト4: 抽出とツリー構造(Family A) ===
print("=== テスト4: 抽出ツリー検証 ===")
from core.svg_renderer import (_extract_shelf_group, _multiply_shelves,
                               _shelf_family, _SHELF_VIEWS, _SHELF_BAND_MARKER)
from utils.path_utils import asset

_NS = "http://www.w3.org/2000/svg"
_NT = f"{{{_NS}}}"
ET.register_namespace("", _NS)


def _load_root(tpl):
    return ET.parse(asset(tpl)).getroot()


def _sub(g, sub_id):
    return next((s for s in g if s.get("id") == sub_id), None)


# 4-1: 各ビューで board/arrow サブグループが生成され、それぞれ path を持つ
root_a = _load_root("template_standard.svg")
for view in _SHELF_VIEWS:
    g = _extract_shelf_group(root_a, "A", view)
    assert g is not None, f"FAIL: shelf-{view} 抽出できない"
    board = _sub(g, f"shelf-{view}-board")
    arrow = _sub(g, f"shelf-{view}-arrow")
    nb = len(list(board)) if board is not None else 0
    na = len(list(arrow)) if arrow is not None else 0
    assert nb >= 1, f"FAIL: shelf-{view} board サブグループが空({nb})"
    assert na >= 1, f"FAIL: shelf-{view} arrow サブグループが空({na})"
    print(f"  OK: shelf-{view} 抽出 board={nb} arrow={na}")

# 4-2: side 帯が section グループに混入していない(C2 回帰防止)
#     section を単独抽出しても、section グループ内に side 帯 marker が無いこと
root_c2 = _load_root("template_standard.svg")
_extract_shelf_group(root_c2, "A", "section")
sec_group = next(g for g in root_c2.iter(f"{_NT}g") if g.get("id") == "shelf-section")
sec_has_side = any("M803.7 209.6" in p.get("d", "") for p in sec_group.iter(f"{_NT}path"))
assert not sec_has_side, "FAIL(C2): side 帯が section グループに混入"
print("  OK: C2 回帰なし(side帯はsectionに混入せず)")

# 4-3: N枚複製で translate 付きグループが各ビュー N 個追加される
for n in (2, 3, 4):
    root_n = _load_root("template_standard.svg")
    spec_n = _spec(tana_count=n)
    _multiply_shelves(root_n, spec_n)
    translated = [g for g in root_n.iter(f"{_NT}g")
                  if g.get("transform", "").startswith("translate")]
    assert len(translated) == n * len(_SHELF_VIEWS), \
        f"FAIL: N={n} translate群={len(translated)} 期待={n*len(_SHELF_VIEWS)}"
    print(f"  OK: N={n} translate群={len(translated)}")

# 4-4: N>=2 では ↕矢印は中央1本のみ(arrow サブグループは据置)・元の板は非表示
#      = 複数棚で各棚に矢印を付けて中央が潰れる不具合の回帰防止
root_arr = _load_root("template_standard.svg")
_multiply_shelves(root_arr, _spec(tana_count=3))
for view in _SHELF_VIEWS:
    grp = next(g for g in root_arr.iter(f"{_NT}g") if g.get("id") == f"shelf-{view}")
    board = _sub(grp, f"shelf-{view}-board")
    arrow = _sub(grp, f"shelf-{view}-arrow")
    assert board is not None and board.get("display") == "none", \
        f"FAIL: shelf-{view} 元の板が非表示になっていない"
    assert arrow is not None and arrow.get("display") != "none", \
        f"FAIL: shelf-{view} 中央矢印が消えている(据置されていない)"
    assert not arrow.get("transform"), \
        f"FAIL: shelf-{view} 中央矢印が移動している(元位置のはず)"
print("  OK: N=3 中央矢印1本据置・元板は非表示(全ビュー)")

# === テスト5: 抽出とツリー構造(Family B) ===
print("=== テスト5: 抽出ツリー検証(Family B) ===")

_B_TEMPLATES = ("template_tobira.svg", "template_tobira_kirikake.svg")

# 5-1: 各テンプレート×各ビューで board/arrow サブグループが生成され、それぞれ path を持つ
for tpl in _B_TEMPLATES:
    root_b = _load_root(tpl)
    for view in _SHELF_VIEWS:
        g = _extract_shelf_group(root_b, "B", view)
        assert g is not None, f"FAIL: {tpl} shelf-{view}(B) 抽出できない"
        board = _sub(g, f"shelf-{view}-board")
        arrow = _sub(g, f"shelf-{view}-arrow")
        nb = len(list(board)) if board is not None else 0
        na = len(list(arrow)) if arrow is not None else 0
        assert nb >= 1, f"FAIL: {tpl} shelf-{view}(B) board 空({nb})"
        assert na >= 1, f"FAIL: {tpl} shelf-{view}(B) arrow 空({na})"
        print(f"  OK: {tpl} shelf-{view}(B) board={nb} arrow={na}")


def _band_marker_str(family, view):
    cfg = _SHELF_BAND_MARKER[(family, view)]
    return cfg if isinstance(cfg, str) else cfg["marker"]


# 5-2: クロスビュー混入防止(B)。_multiply_shelves と同順(front→side→section)で
#     単一 root から3ビューを抽出し、各グループが他ビューの帯 marker を含まないことを
#     テスト4-2(C2 回帰防止)と同じ「含有チェック」方式で確認する。
for tpl in _B_TEMPLATES:
    root_bx = _load_root(tpl)
    groups = {}
    for view in _SHELF_VIEWS:  # front, side, section の順(_multiply_shelves と同順)
        groups[view] = _extract_shelf_group(root_bx, "B", view)
    for view, g in groups.items():
        assert g is not None, f"FAIL: {tpl} shelf-{view}(B) 混入テスト用抽出に失敗"
        other_markers = [_band_marker_str("B", v) for v in _SHELF_VIEWS if v != view]
        for p in g.iter(f"{_NT}path"):
            d = p.get("d", "")
            for om in other_markers:
                assert om not in d, f"FAIL: {tpl} shelf-{view}(B) に他ビュー帯 marker 混入: {om}"
    print(f"  OK: {tpl} クロスビュー混入なし(B)")

# === テスト6: marker 一意性チェック(SVG再エクスポート破壊検知) ===
print("=== テスト6: marker 一意性チェック ===")
from core.svg_renderer import _SHELF_TAIL_SPLIT

_FAMILY_TEMPLATES = {
    "A": ["template_standard.svg", "template_kirikake.svg"],
    "B": ["template_tobira.svg", "template_tobira_kirikake.svg"],
}

_template_text_cache = {}


def _template_text(tpl):
    if tpl not in _template_text_cache:
        with open(asset(tpl), "r", encoding="utf-8") as f:
            _template_text_cache[tpl] = f.read()
    return _template_text_cache[tpl]


_marker_check_count = 0
for key, cfg in _SHELF_BAND_MARKER.items():
    family = key[0]
    marker = cfg if isinstance(cfg, str) else cfg["marker"]
    for tpl in _FAMILY_TEMPLATES[family]:
        text = _template_text(tpl)
        cnt = text.count(marker)
        assert cnt == 1, f"FAIL: band marker {marker!r}({key}) が {tpl} 内で {cnt} 回出現(期待=1)"
        _marker_check_count += 1

for key, cfg in _SHELF_TAIL_SPLIT.items():
    family = key[0]
    marker = cfg["marker"]
    for tpl in _FAMILY_TEMPLATES[family]:
        text = _template_text(tpl)
        cnt = text.count(marker)
        assert cnt == 1, f"FAIL: tail-split marker {marker!r}({key}) が {tpl} 内で {cnt} 回出現(期待=1)"
        _marker_check_count += 1

print(f"  OK: band/tail-split marker 全 {_marker_check_count} 件(テンプレート×marker組)が各ファイルで一意")

# === テスト7: 抽出パスに二重先頭M(MxyMxy)が無い(斜線バグ回帰防止) ===
# 帯末尾の矢印ヘッドが元々絶対M始まりの場合に絶対M起点を前置すると
# "MxyMxy" になり svglib が2つ目の M を直線と誤解釈して斜線を描く不具合の回帰防止。
print("=== テスト7: 二重先頭M 回帰防止 ===")
import re as _re7
_LEAD_DOUBLE_M = _re7.compile(r"^M-?[\d.]+[ ,]-?[\d.]+M")
_dbl_checked = 0
for tpl, fam in [("template_standard.svg", "A"), ("template_kirikake.svg", "A"),
                 ("template_tobira.svg", "B"), ("template_tobira_kirikake.svg", "B")]:
    r = _load_root(tpl)
    for view in _SHELF_VIEWS:
        g = _extract_shelf_group(r, fam, view)
        for p in g.iter(f"{_NT}path"):
            d = p.get("d", "")
            assert not _LEAD_DOUBLE_M.match(d), \
                f"FAIL: {tpl} shelf-{view} に二重先頭M(斜線バグ): {d[:40]}"
            _dbl_checked += 1
print(f"  OK: 抽出パス {_dbl_checked} 本に二重先頭M なし")

# === テスト8: 棚板 board は上下2端(水平線が2つの y 高さ)を持つ(単線化バグ回帰防止) ===
# Family B 側面図で marker が板の下端からで上端を取りこぼし、board が単線化した不具合の回帰防止。
print("=== テスト8: board 二重線(上下端) 検証 ===")


def _horizontal_y_levels(d):
    """パス d 中で水平セグメント(h/H)を描く際の y 値集合(0.5丸め)を返す。"""
    toks = _re7.findall(r"[A-Za-z]|-?\d*\.?\d+", d)
    x = y = 0.0
    cmd = None
    i = 0
    levels = set()
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            continue
        v = float(t)
        if cmd in ("M", "L"):
            x = v; y = float(toks[i + 1]); i += 2; cmd = "L" if cmd == "M" else cmd
        elif cmd in ("m", "l"):
            x += v; y += float(toks[i + 1]); i += 2; cmd = "l" if cmd == "m" else cmd
        elif cmd in ("H", "h"):
            levels.add(round(y * 2) / 2); i += 1
        elif cmd in ("V", "v"):
            y = v if cmd == "V" else y + v; i += 1
        else:
            i += 1
    return levels


_board_checked = 0
for tpl, fam in [("template_standard.svg", "A"), ("template_kirikake.svg", "A"),
                 ("template_tobira.svg", "B"), ("template_tobira_kirikake.svg", "B")]:
    r = _load_root(tpl)
    for view in _SHELF_VIEWS:
        g = _extract_shelf_group(r, fam, view)
        board = _sub(g, f"shelf-{view}-board")
        levels = set()
        for p in board:
            levels |= _horizontal_y_levels(p.get("d", ""))
        assert len(levels) >= 2, \
            f"FAIL: {tpl} shelf-{view} board が単線(水平y高さ {len(levels)}種): 板の上下端を取れていない"
        _board_checked += 1
print(f"  OK: 全 {_board_checked} board が上下2端(水平線2高さ以上)を保持")

print("\n=== Task1 テストPASS ===")
