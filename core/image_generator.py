"""
発注図生成モジュール
SVGテンプレートが利用可能な場合は svg_renderer を優先使用。
テンプレートがない場合は旧 Pillow ベース方式にフォールバック。
"""
import json
import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from core.text_builder import OrderSpec, build_spec_lines, select_base_image
from utils.path_utils import asset, coordinates_path, downloads_dir

# フォント候補（優先順 / Win・Mac・Linux 対応。存在するものが使われる）
_FONT_CANDIDATES = [
    # Windows
    os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "msgothic.ttc"),
    os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "meiryo.ttc"),
    os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "YuGothM.ttc"),
    # macOS（日本語対応）
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    # Linux（Noto / IPA）
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    # 同梱フォント（あれば）
    asset("ipaexg.ttf"),
]


def _get_font(size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size, index=index)
            except Exception:
                continue
    return ImageFont.load_default()


def _load_coords() -> dict:
    path = coordinates_path()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _draw_vertical_text(draw: ImageDraw.ImageDraw, text: str, cfg: dict, font: ImageFont.FreeTypeFont):
    """縦書きテキストを1文字ずつ描画"""
    x = cfg["x"]
    y = cfg["y"]
    pitch = cfg.get("char_pitch", cfg["font_size"])
    color = tuple(cfg["color"])
    for ch in text:
        draw.text((x, y), ch, font=font, fill=color)
        y += pitch


def generate_jpg(spec: OrderSpec, output_path: Optional[str] = None) -> str:
    """
    発注PNGを生成してパスを返す。
    SVGテンプレートが存在する場合は svg_renderer を使用（高精度）。
    output_path が None の場合は Downloads フォルダに保存。
    """
    # ── SVGテンプレート方式（高精度）──────────────────────────────
    from core.svg_renderer import generate_png, _select_template
    tpl_path = asset(_select_template(spec))
    if os.path.exists(tpl_path):
        if output_path is None:
            filename = f"{spec.customer}様宅　洗濯機上吊戸棚.png"
            output_path = os.path.join(downloads_dir(), filename)
        return generate_png(spec, output_path)

    # ── フォールバック: 旧 Pillow ベース方式 ───────────────────────
    coords = _load_coords()

    # --- ベース画像ロード ---
    base_name = select_base_image(spec)
    base_path = asset(base_name)
    if not os.path.exists(base_path):
        raise FileNotFoundError(
            f"ベース画像が見つかりません: {base_path}\n"
            "tools/base_generator.py を実行してベース画像を作成してください。"
        )
    img = Image.open(base_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    dim_cfg = coords["dim_text"]

    # ── W 寸法 ──────────────────────────────────────────────────
    _filler_deduction = {"両側": 40, "左のみ": 20, "右のみ": 20, "なし": 0}
    w_inner = spec.W - _filler_deduction.get(spec.filler, 0)

    def _draw_w(inner_key, total_key):
        if inner_key in dim_cfg and spec.filler != "なし":
            cfg = dim_cfg[inner_key]
            draw.text((cfg["x"], cfg["y"]), str(w_inner),
                      font=_get_font(cfg["font_size"]), fill=tuple(cfg["color"]))
        if total_key in dim_cfg:
            cfg = dim_cfg[total_key]
            draw.text((cfg["x"], cfg["y"]), str(spec.W),
                      font=_get_font(cfg["font_size"]), fill=tuple(cfg["color"]))

    _draw_w("W_inner_top", "W_total_top")
    _draw_w("W_inner", "W_total")

    # フィラー幅「20」テキスト
    ft_cfg = coords.get("filler_text", {})
    _filler_left  = spec.filler in ("両側", "左のみ")
    _filler_right = spec.filler in ("両側", "右のみ")
    for key, draw_it in [
        ("W_inner_top_left",  _filler_left),
        ("W_inner_top_right", _filler_right),
        ("W_inner_bot_left",  _filler_left),
        ("W_inner_bot_right", _filler_right),
    ]:
        if draw_it and key in ft_cfg:
            cfg = ft_cfg[key]
            draw.text((cfg["x"], cfg["y"]), "20",
                      font=_get_font(cfg["font_size"]), fill=tuple(cfg["color"]))

    # ── D 寸法 ──────────────────────────────────────────────────
    if "D_side" in dim_cfg:
        cfg = dim_cfg["D_side"]
        draw.text((cfg["x"], cfg["y"]), str(spec.D),
                  font=_get_font(cfg["font_size"]), fill=tuple(cfg["color"]))

    # ── H 寸法（縦書き） ──────────────────────────────────────
    h_text = str(spec.H)
    h_inner_text = str(spec.H - 30)

    h_draw_pairs = [
        ("H_front_top", h_text),
        ("H_inner_top", h_inner_text),
        ("H_front_bot", h_text),
        ("H_inner_bot", h_inner_text),
        ("H_side_out",  h_text),
        ("H_side_in",   h_inner_text),
    ]
    for key, text in h_draw_pairs:
        if key in dim_cfg:
            cfg = dim_cfg[key]
            draw.text((cfg["x"], cfg["y"]), text,
                      font=_get_font(cfg["font_size"]), fill=tuple(cfg["color"]))

    # --- 仕様テキストブロック ---
    spec_cfg = coords["spec_block"]
    spec_lines = build_spec_lines(spec)
    spec_font = _get_font(spec_cfg["font_size"])
    spec_color = tuple(spec_cfg["color"])
    x = spec_cfg["x"]
    y = spec_cfg["y"]
    lh = spec_cfg["line_height"]
    for line in spec_lines:
        draw.text((x, y), line, font=spec_font, fill=spec_color)
        y += lh

    # --- ハンガーパイプ線（HGあり時） ---
    if spec.hg:
        hp = coords["hanger_pipe_line"]
        draw.line(
            [(hp["x1"], hp["y"]), (hp["x2"], hp["y"])],
            fill=(0, 0, 0),
            width=hp["width"],
        )

    # --- 出力 ---
    if output_path is None:
        filename = f"{spec.customer}様宅　洗濯機上吊戸棚.png"
        output_path = os.path.join(downloads_dir(), filename)

    ext = Path(output_path).suffix.lower()
    if ext == ".png":
        img.save(output_path, "PNG")
    else:
        img.save(output_path, "JPEG", quality=95)
    return output_path
