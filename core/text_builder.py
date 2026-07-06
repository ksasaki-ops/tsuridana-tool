"""
仕様テキストブロックを動的生成するモジュール
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class OrderSpec:
    customer: str           # お客様名
    property_name: str      # 物件名
    W: int                  # 幅（mm）
    D: int                  # 奥行（mm）
    H: int                  # 高さ（mm）
    men_zai_ari: bool       # 面材合わせあり
    tobira_hinban: str      # 扉品番（面材合わせあり時）
    body_material: str      # 本体材質（例：白ポリ）
    filler: str             # "両側" / "左のみ" / "右のみ" / "なし"
    hg: bool                # ハンガーパイプあり
    tobira_enchou: bool     # 扉延長あり
    kirikake: bool          # 切り欠きあり
    kirikake_W: Optional[int] = None   # 切り欠き幅
    kirikake_H: Optional[int] = None   # 切り欠き高さ
    hassou_no: str = ""     # 発注No.
    hassou_date: str = ""   # 発注日
    bikou: str = ""         # 備考
    tana_count: int = 1     # 棚板枚数（1〜4）


# フィラー → テキスト変換
_FILLER_MAP = {
    "両側": ("上部・左・右：フィラー付き", "底面：仕上 白"),
    "左のみ": ("上部・左：フィラー付き", "底面・右：仕上 白"),
    "右のみ": ("上部・右：フィラー付き", "底面・左：仕上 白"),
    "なし": ("上部：フィラー付き", "底面・左・右：仕上 白"),
}


def build_spec_lines(spec: OrderSpec) -> list[str]:
    """仕様テキストブロックの各行リストを返す"""
    dim = f"W{spec.W}xD{spec.D}xH{spec.H}"

    lines = ["洗濯機上吊戸棚", dim]

    if spec.men_zai_ari:
        lines.append(f"扉：{spec.tobira_hinban}")
        lines.append(f"本体・内部・棚板：{spec.body_material}")
    else:
        lines.append(f"扉・本体・内部・棚板：{spec.body_material}")

    lines += [
        f"棚板{spec.tana_count}枚ダボ可動式",
        "耐震ラッチ付き",
        "差し込みダボ",
    ]

    filler_text, bottom_text = _FILLER_MAP.get(spec.filler, (None, "底面・左・右：仕上 白"))
    if filler_text:
        lines.append(filler_text)
    lines.append(bottom_text)

    if spec.hg:
        lines.append("ハンガーパイプ付き")

    if spec.kirikake:
        kw = spec.kirikake_W or 0
        kh = spec.kirikake_H or 0
        lines.append(f"切り欠き有り W{kw}xH{kh}")

    if spec.tobira_enchou:
        lines.append("ハンガーパイプを隠すようの扉延長")

    if spec.bikou:
        lines.append(spec.bikou)

    return lines


def select_base_image(spec: OrderSpec) -> str:
    """仕様に応じたベース画像ファイル名を返す"""
    if spec.tobira_enchou and spec.kirikake:
        return "base_tobira_kirikake.jpg"
    if spec.tobira_enchou:
        return "base_tobira.jpg"
    if spec.kirikake:
        return "base_kirikake.jpg"
    return "base_standard.jpg"
