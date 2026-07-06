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
                               _shelf_family, _SHELF_VIEWS)
from utils.path_utils import asset

_NS = "http://www.w3.org/2000/svg"
_NT = f"{{{_NS}}}"
ET.register_namespace("", _NS)


def _load_root(tpl):
    return ET.parse(asset(tpl)).getroot()


# 4-1: 各ビューで棚板グループが生成され、子要素を最低3つ(帯+矢印)持つ
root_a = _load_root("template_standard.svg")
for view in _SHELF_VIEWS:
    g = _extract_shelf_group(root_a, "A", view)
    assert g is not None, f"FAIL: shelf-{view} 抽出できない"
    n_children = len(list(g))
    assert n_children >= 3, f"FAIL: shelf-{view} 子要素不足({n_children})"
    print(f"  OK: shelf-{view} 抽出 子要素={n_children}")

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

print("\n=== Task1 テストPASS ===")
