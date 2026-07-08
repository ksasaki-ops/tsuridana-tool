"""N=1 出力がベースライン(改修前)とピクセル一致するか検証。
_multiply_shelves は N=1 で早期returnし棚板抽出を行わない(人間承認済みの仕様変更)。
そのため本テストは抽出の非破壊性検証ではなく、text_builder 変更等を含む
N=1 の generate_png パイプライン出力が改修前ベースラインと完全一致することを
保証する後方互換性(完全一致)回帰ガードである。"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.argv[0] = os.path.join(ROOT, "tsuridana.py")
from PIL import Image, ImageChops
from tools.gen_shelf_samples import TEMPLATE_SPECS, _spec
from core.svg_renderer import generate_png

base_dir = os.path.join(ROOT, "test", "shelf_baseline")
fail = False
for name, ov in TEMPLATE_SPECS.items():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        out = tf.name
    try:
        generate_png(_spec(1, **ov), out)
        a = Image.open(os.path.join(base_dir, f"{name}.png")).convert("RGB")
        b = Image.open(out).convert("RGB")
        bbox = ImageChops.difference(a, b).getbbox()
        if bbox is None:
            print(f"  OK: {name} ピクセル一致")
        else:
            print(f"  FAIL: {name} 差分 bbox={bbox}")
            fail = True
    finally:
        if os.path.exists(out):
            os.unlink(out)
sys.exit(1 if fail else 0)
