"""
各SVGテンプレートの棚板帯・↕矢印パスを機械的に検出して表示する開発補助ツール。

使い方:
    py -3 tools/find_shelf_paths.py assets/template_standard.svg
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

_NS = "http://www.w3.org/2000/svg"
_NT = f"{{{_NS}}}"

ARROW_DELTA = re.compile(r"l-?3\.[67]-?1[34]\.[78]")  # 三角矢印ヘッドの斜辺


def main(path):
    tree = ET.parse(path)
    root = tree.getroot()
    print(f"# {os.path.basename(path)}")
    for elem in root.iter(f"{_NT}path"):
        d = elem.get("d", "")
        cls = elem.get("class", "")
        hit = []
        if ARROW_DELTA.search(d):
            hit.append("ARROWHEAD")
        if re.match(r"^M[\d.]+ [\d.]+v", d) and d.count("v") >= 3 and "h" not in d[:40]:
            hit.append("SHAFT?")
        # 絶対M境界の一覧（融合パス検出用）
        abs_ms = re.findall(r"M[\d.]+ [\d.]+", d)
        if hit:
            print(f"[{','.join(hit)}] class={cls}")
            print(f"    d(head)={d[:90]}...")
            if len(abs_ms) > 1:
                print(f"    絶対M境界({len(abs_ms)}): {abs_ms[:6]}")


if __name__ == "__main__":
    main(sys.argv[1])
