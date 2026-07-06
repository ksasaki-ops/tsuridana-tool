"""
SVGテンプレートからPNGを生成するモジュール
- svglib で寸法線・矢印・数字を正確にレンダリング
- PIL で日本語テキストを正確な位置にオーバーレイ
"""
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from reportlab.graphics import renderPM
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from svglib.svglib import svg2rlg

from core.text_builder import OrderSpec, build_spec_lines
from utils.path_utils import asset, downloads_dir

# SVGの名前空間
_NS = "http://www.w3.org/2000/svg"
_NT = f"{{{_NS}}}"  # タグプレフィックス

# テンプレートSVGの元スペック（W760xD450xH600, 両側フィラー）
_TPL_H = 600
_TPL_H_INNER = 570   # H - 30
_TPL_H_LOWER = 590   # H - 10（標準テンプレートのみ）
_TPL_H_DOOR = 580    # H - 20（扉延長テンプレートのみ）
_TPL_W = 760
_TPL_W_INNER = 720   # W - 40（両側フィラー20×2）
_TPL_D = 450
_TPL_KIRIKAKE_W = 230
_TPL_KIRIKAKE_H = 150

# レンダリングDPI（出力解像度）
_DPI = 200

# reportlab にシステムフォントを登録（exe環境でfreetype解決エラーを回避）
_FONT_REGISTERED = False


def _register_reportlab_fonts():
    """reportlab/freetype が使える実フォントを登録する"""
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    _FONT_REGISTERED = True
    windir = os.environ.get("WINDIR", "C:/Windows")
    candidates = [
        os.path.join(windir, "Fonts", "arial.ttf"),
        os.path.join(windir, "Fonts", "msgothic.ttc"),
        os.path.join(windir, "Fonts", "cour.ttf"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                font = TTFont("Helvetica", path)
                pdfmetrics.registerFont(font)
                return
            except Exception:
                continue

# フォント候補（日本語対応）
_FONT_CANDIDATES = [
    os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "msgothic.ttc"),
    os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "meiryo.ttc"),
    os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "YuGothM.ttc"),
    asset("ipaexg.ttf"),
]


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _filler_deduction(spec: OrderSpec) -> int:
    return {"両側": 40, "左のみ": 20, "右のみ": 20, "なし": 0}.get(spec.filler, 0)


def _svg_to_img_coord(svg_x: float, svg_y: float, scale: float):
    """SVG座標(px) → レンダリング後画像座標(px)"""
    return svg_x * scale, svg_y * scale


# ─── SVG テキストノードの寸法値を書き換え ───────────────────────────

def _hide_element(elem):
    """要素を非表示にする（display:none）"""
    elem.set("display", "none")


def _substitute_dimensions(root, spec: OrderSpec):
    """スペックに応じて寸法テキストを置換"""
    h = spec.H
    h_inner = h - 30
    h_lower = h - 10
    w = spec.W
    w_inner = w - _filler_deduction(spec)
    d = spec.D

    # テンプレート元値 → スペック値のマッピング（シングルパス置換）
    # _TPL_H_LOWER(590)は標準SVGのみ、_TPL_H_DOOR(580)は扉延長SVGのみに存在
    dim_map = {
        str(_TPL_H): str(h),
        str(_TPL_H_INNER): str(h_inner),
        str(_TPL_H_LOWER): str(h_lower),
        str(_TPL_H_DOOR): str(h - 20),
        str(_TPL_W): str(w),
        str(_TPL_W_INNER): str(w_inner),
        str(_TPL_D): str(d),
    }

    if spec.kirikake and spec.kirikake_W and spec.kirikake_H:
        dim_map[str(_TPL_KIRIKAKE_W)] = str(spec.kirikake_W)
        dim_map[str(_TPL_KIRIKAKE_H)] = str(spec.kirikake_H)

    for elem in root.iter(f"{_NT}text"):
        txt = (elem.text or "").strip()
        if txt in dim_map and dim_map[txt] != txt:
            elem.text = dim_map[txt] + " "


# ─── フィラー・ハンガーパイプ表示制御 ─────────────────────────────────

_FILLER_RIGHT_IDS = ["filler-right-front", "filler-right-bottom"]
_FILLER_LEFT_IDS = ["filler-left-front", "filler-left-bottom"]


def _control_filler_visibility(root, spec: OrderSpec):
    """フィラーなし側の要素を非表示にする（フィラー本体のみ）"""
    left = spec.filler in ("両側", "左のみ")
    right = spec.filler in ("両側", "右のみ")

    hide_ids = set()
    if not right:
        hide_ids.update(_FILLER_RIGHT_IDS)
    if not left:
        hide_ids.update(_FILLER_LEFT_IDS)

    if hide_ids:
        for elem in root.iter():
            if elem.get("id", "") in hide_ids:
                _hide_element(elem)


_HANGER_PIPE_IDS = {"hanger-pipe", "hanger-pipe-front", "hanger-pipe-bottom"}
_GRAY_IDS = {"filler-left-gray-top", "filler-left-gray-bottom",
             "filler-right-gray-top", "filler-right-gray-bottom"}


def _control_hanger_pipe(root, spec: OrderSpec):
    """ハンガーパイプなし時に横棒+グレー縦棒を全て非表示にする"""
    if not spec.hg:
        target_ids = _HANGER_PIPE_IDS | _GRAY_IDS
        for elem in root.iter():
            if elem.get("id", "") in target_ids:
                _hide_element(elem)


def _standard_filler_pairs(left: bool, right: bool):
    """標準テンプレートのフィラー寸法線座標ペア"""
    pairs = []
    if not left:
        pairs += [
            ("M211.9 351.3", "M219.8 351.3"),
            ("M211.9 435.2", "M219.8 435.2"),
            ("M205.1 435.2", "M213.0 435.2"),
            ("M216.9 430.5", "M224.8 430.5"),
            ("M211.9 796.8", "M219.8 796.8"),
            ("M211.9 861.8", "M219.8 861.8"),
            ("M205.1 861.8", "M213.0 861.8"),
            ("M216.9 856.9", "M224.8 856.9"),
        ]
    if not right:
        pairs += [
            ("M561 384.6", "M553.3 384.6"),
            ("M561 435.2", "M553.3 435.2"),
            ("H561", "H553.3"),
            ("M556.2 440.2", "M548.5 440.2"),
            ("M560.3 798.6", "M552.4 798.6"),
            ("M560.3 861.8", "M552.4 861.8"),
            ("H560.3", "H552.4"),
            ("M555.3 866.6", "M547.4 866.6"),
        ]
    return pairs


def _tobira_filler_pairs(left: bool, right: bool):
    """扉延長テンプレートのフィラー寸法線座標ペア"""
    pairs = []
    if not left:
        pairs += [
            # 正面図（dimline-total-width-front）
            ("M205.1 404.4", "M213.0 404.4"),
            ("M198.2 473.9", "M206.1 473.9"),
            ("M209.9 469.2", "M217.8 469.2"),
            ("M205.1 473.9H", "M213.0 473.9H"),
            # 底面図（dimline-total-width-bottom）
            ("M205.1 805.6", "M213.0 805.6"),
            ("M198.2 863.5", "M206.1 863.5"),
            ("M209.9 858.7", "M217.8 858.7"),
            ("M205.1 863.5H", "M213.0 863.5H"),
        ]
    if not right:
        pairs += [
            # 正面図（dimline-total-width-front）
            ("M554.2 423.5", "M546.3 423.5"),
            ("M554.2 473.9H561", "M546.3 473.9H553.3"),
            ("M549.3 478.9", "M541.4 478.9"),
            # 底面図（dimline-total-width-bottom）
            ("M554.2 805.6", "M546.3 805.6"),
            ("M554.2 863.5H561", "M546.3 863.5H553.3"),
            ("M549.3 868.4", "M541.4 868.4"),
        ]
    return pairs


def _adjust_dimlines_for_filler(root, spec: OrderSpec):
    """フィラーなし側の総幅寸法線を内壁座標に合わせる"""
    left = spec.filler in ("両側", "左のみ")
    right = spec.filler in ("両側", "右のみ")

    # フィラーなし → 内寸=総幅なので下段寸法線を非表示
    if not left and not right:
        for elem in root.iter():
            if elem.get("id", "") in {"dimline-total-width-front", "dimline-total-width-bottom"}:
                _hide_element(elem)
        return

    if left and right:
        return

    if spec.tobira_enchou:
        pairs = _tobira_filler_pairs(left, right)
    else:
        pairs = _standard_filler_pairs(left, right)

    for elem in root.iter(f"{_NT}path"):
        d = elem.get("d", "")
        if elem.get("display") == "none":
            continue
        changed = False
        for old, new in pairs:
            if old in d:
                d = d.replace(old, new)
                changed = True
        if changed:
            elem.set("d", d)


# ─── 日本語テキストのオーバーレイ ───────────────────────────────────

def _draw_spec_block(draw: ImageDraw.ImageDraw, spec: OrderSpec,
                     svg_w: float, svg_h: float, img_w: int, img_h: int):
    """仕様テキストブロックを PIL で描画"""
    scale = img_w / svg_w

    # 背景を白塗り（SVG の背景矩形に合わせる）
    bg_x1 = 736.1 * scale
    bg_y1 = 569.1 * scale
    bg_x2 = 962.0 * scale
    if spec.tobira_enchou and spec.kirikake:
        bg_y2 = 820.0 * scale
    elif spec.tobira_enchou or spec.kirikake:
        bg_y2 = 800.0 * scale
    else:
        bg_y2 = 783.0 * scale
    draw.rectangle([bg_x1, bg_y1, bg_x2, bg_y2], fill=(255, 255, 255))

    # フォントサイズ: SVGのfont-size 21.27px × scale
    font_size = max(10, int(21.27 * scale))
    font = _get_font(font_size)
    line_height = int(21.3 * scale)

    lines = build_spec_lines(spec)
    # 1行目: "洗濯機上吊戸棚" → spec block line[0]
    # 2行目: "W...xD...xH..." → line[1] (ASCII, すでに svglib で描画されているが再描画で確実にする)
    x = bg_x1
    y = 587.6 * scale - font_size  # y は SVG のベースライン座標

    for line in lines:
        draw.text((x, y), line, font=font, fill=(0, 0, 0))
        y += line_height


def _draw_taishin_labels(draw: ImageDraw.ImageDraw, spec: OrderSpec,
                         svg_w: float, svg_h: float, img_w: int, img_h: int):
    """「耐震ラッチ」ラベル×3を PIL で描画（青）"""
    scale = img_w / svg_w

    font_size = max(8, int(13.75 * scale))
    font = _get_font(font_size)
    color = (0, 0, 0xDD)  # #00D

    if spec.tobira_enchou:
        positions = [
            (934.6, 46.2),   # 側面図
            (509.7, 44.9),   # 正面図（上）
            (476.9, 508.2),  # 正面図（下）
        ]
    else:
        positions = [
            (934.6, 46.2),   # 側面図
            (516.5, 44.9),   # 正面図（上）
            (516.5, 475.6),  # 正面図（下）
        ]
    for sx, sy in positions:
        ix = sx * scale
        iy = (sy - 13.75) * scale
        draw.text((ix, iy), "耐震ラッチ", font=font, fill=color)


def _draw_hg_labels(img: Image.Image,
                    svg_w: float, svg_h: float, img_w: int, img_h: int):
    """「HGが隠れる寸法」ラベルを90°回転でPIL描画（赤）"""
    scale = img_w / svg_w

    font_size = max(8, int(13.75 * scale))
    font = _get_font(font_size)
    color = (0xDD, 0, 0)  # #D00

    label = "HGが隠れる寸法"

    # テキストサイズを測定
    bbox = font.getbbox(label)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    # 一時画像にテキスト描画 → 90°反時計回り回転
    tmp = Image.new("RGBA", (tw + 4, th + 4), (255, 255, 255, 0))
    tmp_draw = ImageDraw.Draw(tmp)
    tmp_draw.text((2, 2), label, font=font, fill=color)
    rotated = tmp.rotate(90, expand=True)

    # SVG transform matrix(0 -1 1 0 tx ty) = 90°反時計回り回転
    # テキスト位置: (154.5, 413.6) 正面図左、(753.7, 413.6) 側面図右
    positions = [
        (154.5, 413.6),  # 正面図左
        (753.7, 413.6),  # 側面図右
    ]
    rw, rh = rotated.size
    for sx, sy in positions:
        ix = int(sx * scale) - rw // 2
        iy = int(sy * scale) - rh
        img.paste(rotated, (ix, iy), rotated)


def _draw_kirikake_labels(draw: ImageDraw.ImageDraw,
                          svg_w: float, svg_h: float, img_w: int, img_h: int):
    """「切り欠き加工」ラベルをPILで描画（切り欠き単体用）"""
    scale = img_w / svg_w
    font_size = max(8, int(18.33 * scale))
    font = _get_font(font_size)
    ix = 1040.8 * scale
    iy = (66.9 - 18.33) * scale
    draw.text((ix, iy), "切り欠き加工", font=font, fill=(0, 0, 0))


def _draw_kirikake_labels_tobira(draw: ImageDraw.ImageDraw,
                                  svg_w: float, svg_h: float, img_w: int, img_h: int):
    """「切り欠き加工」ラベルをPILで描画（tobira+kirikake用）"""
    scale = img_w / svg_w
    font_size = max(8, int(18.33 * scale))
    font = _get_font(font_size)
    ix = 1040.8 * scale
    iy = (66.9 - 18.33) * scale
    draw.text((ix, iy), "切り欠き加工", font=font, fill=(0, 0, 0))


def _hide_japanese_in_svg(root):
    """svglib レンダリング前に日本語テキスト要素を非表示にする"""
    for elem in root.iter(f"{_NT}text"):
        txt = (elem.text or "").strip()
        if any(ord(c) > 127 for c in txt):
            _hide_element(elem)


def _strip_font_face(root):
    """@font-face と font-family を除去（exe環境でフォント解決エラーを回避）"""
    for style_elem in root.iter(f"{_NT}style"):
        txt = style_elem.text or ""
        # @font-face ブロックを除去
        txt = re.sub(r"@font-face\s*\{[^}]*\}", "", txt)
        # CSS クラス内の font-family 宣言を除去
        txt = re.sub(r"font-family:\s*[^;]+;", "", txt)
        style_elem.text = txt


# ─── メイン生成関数 ────────────────────────────────────────────────

# ─── 棚板複製ロジック ───────────────────────────────────────────────
# 注: re は本ファイル冒頭(line 7)で import 済み。別名は作らない。

# 英字は全て1トークンとして捕捉する。M m L l H h V v Z z 以外(C/S/Q/T/A 等)が
# 出現したら下の else 分岐で ValueError を送出する(黙って取りこぼさない)。
_PATH_TOKEN = re.compile(r"([A-Za-z])|(-?\d*\.?\d+)")


def _path_end_point(d: str):
    """パスデータ d を辿った終端の絶対座標 (x, y) を返す。対応: M m L l H h V v Z z。
    それ以外のコマンド(曲線・円弧等)は ValueError。"""
    tokens = []
    for m in _PATH_TOKEN.finditer(d):
        if m.group(1):
            tokens.append(m.group(1))
        else:
            tokens.append(float(m.group(2)))

    x = y = 0.0
    start_x = start_y = 0.0
    i = 0
    cmd = None
    while i < len(tokens):
        t = tokens[i]
        if isinstance(t, str):
            cmd = t
            i += 1
            if cmd in ("Z", "z"):
                x, y = start_x, start_y
            continue
        if cmd is None:
            raise ValueError(f"数値がコマンド無しで出現: {d[:40]}")
        if cmd in ("M", "L"):
            x, y = tokens[i], tokens[i + 1]; i += 2
            if cmd == "M":
                start_x, start_y = x, y
                cmd = "L"  # 以降の座標対は暗黙 LineTo
        elif cmd in ("m", "l"):
            x += tokens[i]; y += tokens[i + 1]; i += 2
            if cmd == "m":
                start_x, start_y = x, y
                cmd = "l"
        elif cmd == "H":
            x = tokens[i]; i += 1
        elif cmd == "h":
            x += tokens[i]; i += 1
        elif cmd == "V":
            y = tokens[i]; i += 1
        elif cmd == "v":
            y += tokens[i]; i += 1
        else:
            raise ValueError(f"未対応コマンド: {cmd}")
    return x, y


_SHELF_VIEWS = ("front", "side", "section")

_SHELF_CENTER = {
    ("A", "front"): 218.25, ("A", "side"): 213.95, ("A", "section"): 656.9,
    ("B", "front"): 226.35, ("B", "side"): 247.95, ("B", "section"): 657.15,
}
_SHELF_CAVITY = {
    ("A", "front"): (105.0, 340.0), ("A", "side"): (110.0, 333.8),
    ("A", "section"): (539.2, 766.5),
    ("B", "front"): (105.0, 344.0), ("B", "side"): (110.0, 333.8),
    ("B", "section"): (539.2, 766.0),
}


def _shelf_family(spec: OrderSpec) -> str:
    return "B" if spec.tobira_enchou else "A"


def _shelf_targets(family: str, view: str, n: int) -> list:
    """内寸を(n+1)等分した絶対 y 目標位置リスト"""
    top, bottom = _SHELF_CAVITY[(family, view)]
    return [top + i / (n + 1) * (bottom - top) for i in range(1, n + 1)]


# 棚板帯 marker（ホストパス d 内で棚板帯部が始まる位置の一意な部分文字列）。
#   値は str（絶対M始まり=そのまま帯 d に採用）または
#   dict {"marker": 区切り, "abs": bool}。abs=False の場合は marker が相対始まり
#   なので、直前までを辿った絶対座標を _path_end_point で求めて M を前置する。
# Family A: 帯は箱枠パス内に絶対M subpath として融合（絶対M）。
# Family B: 帯は箱枠/格子パス内に相対 subpath として融合（abs=False で絶対M付与）。
_SHELF_BAND_MARKER = {
    ("A", "front"):   "M537.7 227",
    ("A", "side"):    "M803.7 209.6",
    ("A", "section"): "M544.7 661.3",
    ("B", "front"):   {"marker": "m158 126.7", "abs": False},
    ("B", "side"):    {"marker": "V248m0 0H954.4", "abs": False},
    ("B", "section"): {"marker": "m-8.6-118.1", "abs": False},
}
# 矢印ヘッド/シャフト独立パスの先頭一致プレフィックス（上矢/下矢/シャフト）
_SHELF_ARROW_PREFIX = {
    ("A", "front"):   ["M302.7 203.9", "M310 232.7", "M306.3 190.1"],
    ("A", "side"):    ["M886.6 197.8", "M893.9 226.6", "M890.3 184.1"],
    ("A", "section"): ["M302.7 646.8", "M310 675.6", "M306.3 633"],
    ("B", "front"):   ["M295.9 211.9", "M303.2 240.7", "M299.6 198.2"],
    ("B", "side"):    ["M886.6 233.6", "M893.9 262.4", "M890.3 219.8"],
    ("B", "section"): ["M295.9 642.8", "M303.2 671.6", "M299.6 629"],
}
# パス内で棚板と無関係な後続部を切り離すための「絶対Mまたは相対」区切り。
#   {"marker": 区切り文字列, "abs": True=区切りが絶対Mなのでそのまま body に残す /
#                                   False=相対始まりなので _path_end_point で絶対M付与}
_SHELF_TAIL_SPLIT = {
    # section shaft は line204 で side 帯と融合。side 帯(絶対M)を body に残す
    ("A", "section", "M306.3 633"): {"marker": "M803.7 209.6", "abs": True},
    # front shaft は line99 で dowel マーカーと融合。dowel は相対 m 始まり
    ("A", "front", "M306.3 190.1"): {"marker": "m92.1-137.9", "abs": False},
    # B front シャフトは dowel と融合（相対 m 始まり）
    ("B", "front", "M299.6 198.2"): {"marker": "m92-146", "abs": False},
    # B side シャフトは dowel と融合（dowel は絶対 M 始まり）
    ("B", "side", "M890.3 219.8"): {"marker": "M816.6 110", "abs": True},
    # B section シャフト(M299.6 629)は融合なし（分割不要）
}
_NT_PATH = f"{_NT}path"


def _shelf_body_class(family: str) -> str:
    return "g5" if family == "A" else "g3"


def _split_tail(elem, split_cfg):
    """elem の d を split_cfg["marker"] で分割。前半を elem に残し(→呼び出し側で group へ移動)、
    後半(tail)は body に残すための新規 <path> を生成して返す。tail が相対始まりなら絶対M付与。
    融合していなければ(marker 不在) None を返す。"""
    d = elem.get("d", "")
    marker = split_cfg["marker"]
    if marker not in d:
        return None  # 融合していない個体（kirikake 等で形状差がある場合の安全策）
    si = d.index(marker)
    head_d, tail_d = d[:si], d[si:]
    elem.set("d", head_d)
    if not split_cfg["abs"]:
        ex, ey = _path_end_point(head_d)
        tail_d = f"M{ex:.4f} {ey:.4f}" + tail_d  # 相対始まりに絶対起点を付与
    tail = ET.Element(_NT_PATH)
    tail.set("d", tail_d)
    if elem.get("class"):
        tail.set("class", elem.get("class"))
    return tail


def _extract_shelf_group(root, family: str, view: str):
    gid = f"shelf-{view}"
    for g in root.iter(f"{_NT}g"):
        if g.get("id") == gid:
            return g

    body_cls = _shelf_body_class(family)
    parent_map = {c: p for p in root.iter() for c in p}
    group = ET.Element(f"{_NT}g")
    group.set("id", gid)
    moved_any = False
    # z-order 保持: 元の棚板クラスタ位置に group を差し込む(root 末尾ではなく)。
    # brief M1 注記のとおり root.append すると対角センター線との交差で
    # アンチエイリアスが微差する為、原位置へ挿入して非破壊性を担保する。
    inserted = False

    def _insert_group_at(parent, index):
        nonlocal inserted
        if inserted or parent is None:
            return
        index = max(0, min(index, len(list(parent))))
        parent.insert(index, group)
        inserted = True

    # 1) 棚板帯をホストパスから切り出し（絶対M分割 or 相対 marker→絶対M付与）
    band_cfg = _SHELF_BAND_MARKER.get((family, view))
    if band_cfg is not None:
        if isinstance(band_cfg, str):
            marker, band_abs = band_cfg, True
        else:
            marker, band_abs = band_cfg["marker"], band_cfg["abs"]
        for elem in list(root.iter(f"{_NT}path")):
            d = elem.get("d", "")
            if marker in d:
                idx = d.index(marker)
                parent = parent_map.get(elem)
                band_class = elem.get("class") or body_cls
                if idx == 0:
                    # ホストパス全体が帯（例: section line200）→ パスごと group へ移動し
                    #   body に空 d="" を残さない。原位置に group を差し込む。
                    if parent is not None:
                        _insert_group_at(parent, list(parent).index(elem))
                        parent.remove(elem)
                    if not elem.get("class"):
                        elem.set("class", body_cls)
                    group.append(elem)
                else:
                    head_d = d[:idx]
                    tail_d = d[idx:]
                    elem.set("d", head_d)         # body 側（帯より前）を残す
                    if not band_abs:
                        # 相対始まりの帯に絶対起点 M を前置（standalone として妥当に）
                        ex, ey = _path_end_point(head_d)
                        tail_d = f"M{ex:.4f} {ey:.4f}" + tail_d
                    # host の直後に group を差し込む（帯は元々 host の末尾に描画）
                    if parent is not None:
                        _insert_group_at(parent, list(parent).index(elem) + 1)
                    band = ET.SubElement(group, _NT_PATH)
                    band.set("d", tail_d)         # 絶対M始まり
                    band.set("class", band_class)
                moved_any = True
                break

    # 2) 矢印ヘッド/シャフトの独立パスを回収（融合パスは分割）
    prefixes = _SHELF_ARROW_PREFIX.get((family, view), [])
    for elem in list(root.iter(f"{_NT}path")):
        d = elem.get("d", "")
        matched = next((p for p in prefixes if d.startswith(p)), None)
        if matched is None:
            continue
        split_cfg = _SHELF_TAIL_SPLIT.get((family, view, matched))
        parent = parent_map.get(elem)
        if parent is not None and not inserted:
            _insert_group_at(parent, list(parent).index(elem))
        if split_cfg:
            tail = _split_tail(elem, split_cfg)
            if tail is not None and parent is not None:
                # tail は body に残すが、クラスタの z 位置（group 直後）に置く
                if inserted and group in list(parent):
                    parent.insert(list(parent).index(group) + 1, tail)
                else:
                    parent.append(tail)
        if parent is not None:
            parent.remove(elem)
        group.append(elem)
        moved_any = True

    if not moved_any:
        return None
    if not inserted:
        root.append(group)
    return group


def _multiply_shelves(root, spec: OrderSpec):
    """全ビューで棚板グループを抽出し、tana_count>=2 なら均等割りで複製する。

    N=1 は非破壊で描画する必要がある(ベースライン=改修前と完全一致が製品要件)。
    棚板帯は正面図ではホストパスの箱枠+ダボ格子の破線と 1 ストローク内で融合して
    ラスタライズされており、帯を別 <path> に切り出すと重なり画素のアンチエイリアス
    合成が変わり ≤18 画素(最大 delta 39/255、視認不能)の差分が不可避に生じる
    (同一 z へその場分割しても同差分が出ることを確認済み)。
    従って N=1 では抽出(破壊的分割)を行わずテンプレートをそのまま描画する。
    抽出そのものの構造検証は test_shelf_count.py テスト4 で、N>=2 の見た目は
    gen_shelf_samples.py の目視で担保する。"""
    import copy
    n = getattr(spec, "tana_count", 1) or 1
    if n <= 1:
        return  # N=1 は改修前と完全一致（破壊的な帯分割を行わない）
    family = _shelf_family(spec)
    for view in _SHELF_VIEWS:
        group = _extract_shelf_group(root, family, view)
        if group is None:
            continue
        center = _SHELF_CENTER[(family, view)]
        _hide_element(group)
        for ty in _shelf_targets(family, view, n):
            dy = ty - center
            clone = copy.deepcopy(group)
            clone.attrib.pop("id", None)
            clone.attrib.pop("display", None)
            clone.set("transform", f"translate(0 {dy:.3f})")
            root.append(clone)


def _select_template(spec: OrderSpec) -> str:
    """スペックに応じたSVGテンプレートファイル名を返す"""
    if spec.tobira_enchou and spec.kirikake:
        return "template_tobira_kirikake.svg"
    if spec.tobira_enchou:
        return "template_tobira.svg"
    if spec.kirikake:
        return "template_kirikake.svg"
    return "template_standard.svg"


def generate_png(spec: OrderSpec, output_path: Optional[str] = None) -> str:
    """
    SVGテンプレートから PNG を生成してパスを返す。
    output_path が None の場合は Downloads フォルダに保存。
    """
    if output_path is None:
        filename = f"{spec.customer}様宅　洗濯機上吊戸棚.png"
        output_path = os.path.join(downloads_dir(), filename)

    # ── reportlab フォント登録（exe環境対策） ─────────────────────
    _register_reportlab_fonts()

    # ── テンプレート読み込み ──────────────────────────────────────
    tpl_name = _select_template(spec)
    tpl_path = asset(tpl_name)
    if not os.path.exists(tpl_path):
        raise FileNotFoundError(
            f"SVGテンプレートが見つかりません: {tpl_path}\n"
            f"assets/{tpl_name} を配置してください。"
        )

    ET.register_namespace("", _NS)
    tree = ET.parse(tpl_path)
    root = tree.getroot()

    svg_w = float(root.get("width", 1286))
    svg_h = float(root.get("height", 909))

    # ── 寸法値置換 ────────────────────────────────────────────────
    _substitute_dimensions(root, spec)

    # ── フィラー・ハンガーパイプ表示制御 ──────────────────────────
    _control_filler_visibility(root, spec)
    _adjust_dimlines_for_filler(root, spec)
    _control_hanger_pipe(root, spec)

    # ── 棚板 抽出 & N 枚複製 ───────────────────────────────────────
    _multiply_shelves(root, spec)

    # ── 日本語テキストを非表示（svglib はレンダリング不可） ──────
    _hide_japanese_in_svg(root)

    # ── @font-face を除去（exe 環境でのフォント解決エラー回避） ──
    _strip_font_face(root)

    # ── 修正済みSVGを一時ファイルに書き出し ──────────────────────
    with tempfile.NamedTemporaryFile(
        suffix=".svg", delete=False, mode="w", encoding="utf-8"
    ) as f:
        tmp_path = f.name
        tree.write(f, encoding="unicode", xml_declaration=False)

    try:
        # ── svglib でレンダリング ─────────────────────────────────
        drawing = svg2rlg(tmp_path)
        if drawing is None:
            raise RuntimeError("svglib: SVGの読み込みに失敗しました")
        img = renderPM.drawToPIL(drawing, dpi=_DPI)
    finally:
        os.unlink(tmp_path)

    img_w, img_h = img.size
    draw = ImageDraw.Draw(img)

    # ── 日本語テキストを PIL でオーバーレイ ───────────────────────
    _draw_spec_block(draw, spec, svg_w, svg_h, img_w, img_h)
    _draw_taishin_labels(draw, spec, svg_w, svg_h, img_w, img_h)
    if spec.tobira_enchou:
        _draw_hg_labels(img, svg_w, svg_h, img_w, img_h)
    if spec.kirikake:
        if spec.tobira_enchou:
            _draw_kirikake_labels_tobira(draw, svg_w, svg_h, img_w, img_h)
        else:
            _draw_kirikake_labels(draw, svg_w, svg_h, img_w, img_h)

    img.save(output_path, "PNG")
    return output_path
