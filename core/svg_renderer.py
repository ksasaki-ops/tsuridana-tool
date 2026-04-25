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
