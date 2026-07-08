"""
棚板サンプル/ベースライン画像生成

使い方:
    py -3 tools/gen_shelf_samples.py baseline   # 改修前 N=1 ベースライン(4枚)
    py -3 tools/gen_shelf_samples.py samples     # N=2,3,4 サンプル(12枚)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.argv[0] = os.path.join(ROOT, "tsuridana.py")

from core.text_builder import OrderSpec
from core.svg_renderer import generate_png

TEMPLATE_SPECS = {
    "standard":        dict(hg=False, tobira_enchou=False, kirikake=False),
    "kirikake":        dict(hg=False, tobira_enchou=False, kirikake=True,
                            kirikake_W=120, kirikake_H=83),
    "tobira":          dict(hg=True,  tobira_enchou=True,  kirikake=False),
    "tobira_kirikake": dict(hg=True,  tobira_enchou=True,  kirikake=True,
                            kirikake_W=82, kirikake_H=123),
}


def _spec(tana_count, **overrides):
    base = dict(
        customer="サンプル", property_name="",
        W=801, D=450, H=600,
        men_zai_ari=True, tobira_hinban="WS-3091E",
        body_material="白ポリ", filler="両側",
        hg=False, tobira_enchou=False, kirikake=False,
        tana_count=tana_count,
    )
    base.update(overrides)
    return OrderSpec(**base)


def gen_baseline():
    out_dir = os.path.join(ROOT, "test", "shelf_baseline")
    os.makedirs(out_dir, exist_ok=True)
    for name, ov in TEMPLATE_SPECS.items():
        generate_png(_spec(1, **ov), os.path.join(out_dir, f"{name}.png"))
        print(f"  baseline: {name}.png")


def gen_samples():
    out_dir = os.path.join(ROOT, "test", "shelf_samples")
    os.makedirs(out_dir, exist_ok=True)
    for name, ov in TEMPLATE_SPECS.items():
        for n in (2, 3, 4):
            generate_png(_spec(n, **ov), os.path.join(out_dir, f"{name}_{n}mai.png"))
            print(f"  sample: {name}_{n}mai.png")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    if mode == "baseline":
        gen_baseline()
    elif mode == "samples":
        gen_samples()
    else:
        print(f"unknown mode: {mode}"); sys.exit(1)
    print("=== 完了 ===")
