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

print("\n=== Task1 テストPASS ===")
