# make_kml_from_observation.py
# フォルダ内のTXTから Observation* の四隅 (UL/UR/LL/LR) の緯度経度を抽出し、
# Google Earth で表示できる KML を生成します。

import argparse
import glob
import os
import re
from xml.sax.saxutils import escape

# 角の並び（UL→UR→LR→LL→UL で閉じる）
CORNERS = [
    ("Upper", "Left"),
    ("Upper", "Right"),
    ("Lower", "Right"),
    ("Lower", "Left"),
    ("Upper", "Left"),  # ring close
]

def _rx_from_words(*words):
    """
    複数の語の間に任意の非英数字（空白、アンダースコア等）を許す柔らかい正規表現を作る。
    例: Observation Upper Left Latitude Degree
       -> r'Observation\W*Upper\W*Left\W*Latitude\W*Degree'
    """
    return r"\W*".join(map(re.escape, words))

def _find_number_by_variants(text, corner_words, coord_words):
    """
    Observation + corner + coord の語群から、Degree 有無など複数バリアントで検索。
    corner_words 例: ["Upper","Left"] / coord_words 例: ["Latitude"] or ["Longitude"]
    """
    # 優先順に試す（Degree あり→なし）
    variants = [
        ["Observation"] + corner_words + coord_words + ["Degree"],
        ["Observation"] + corner_words + coord_words,
    ]
    for words in variants:
        pat = _rx_from_words(*words) + r"\s*=\s*([+-]?\d+(?:\.\d+)?)"
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None

def parse_one_file(filepath):
    # 文字コードはまずUTF-8、ダメならcp932を試す
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        with open(filepath, "r", encoding="cp932", errors="ignore") as f:
            text = f.read()

    base = os.path.basename(filepath)
    # 先頭の番号（ラベル）
    m_label = re.match(r"(\d+)_", base)
    label = int(m_label.group(1)) if m_label else None

    # ProductID（説明用）
    m_pid = re.search(r'ProductID\s*=\s*"([^"]+)"', text)
    product_id = m_pid.group(1) if m_pid else os.path.splitext(base)[0]

    # 四隅の観測座標を抽出
    lons = []
    lats = []
    for (v1, v2) in CORNERS:
        # Latitude
        lat = _find_number_by_variants(text, [v1, v2], ["Latitude"])
        # Longitude
        lon = _find_number_by_variants(text, [v1, v2], ["Longitude"])
        if lat is None or lon is None:
            raise ValueError(
                f"Missing Observation {v1} {v2} Latitude/Longitude in {base}"
            )
        lats.append(lat)
        lons.append(lon)

    # 中心（BBoxの中心）
    cx = (min(lons[:-1]) + max(lons[:-1])) / 2.0
    cy = (min(lats[:-1]) + max(lats[:-1])) / 2.0

    return {
        "filepath": filepath,
        "label": label,
        "product_id": product_id,
        "lons": lons,  # 5点（最後は最初の点の繰り返し）
        "lats": lats,
        "cx": cx,
        "cy": cy,
    }

def collect_records(indir):
    files = sorted(glob.glob(os.path.join(indir, "*.txt")), key=lambda p: p.lower())
    recs = []
    for fp in files:
        try:
            rec = parse_one_file(fp)
            recs.append(rec)
        except Exception as e:
            print(f"[WARN] Skip {os.path.basename(fp)}: {e}")
    # ラベル昇順（ラベル無しは末尾）
    recs.sort(key=lambda r: (9999 if r["label"] is None else r["label"]))
    return recs

def write_kml(records, out_kml):
    if not records:
        raise RuntimeError("No valid records to export as KML.")

    # KML colors (aabbggrr)
    style_colors = [
        ("cc0000ff", "330000ff"),  # red
        ("cc00ffff", "3300ffff"),  # cyan
        ("cc00ff00", "3300ff00"),  # green
        ("ccffff00", "33ffff00"),  # yellow
        ("ccff00ff", "33ff00ff"),  # magenta
        ("ccff7f00", "33ff7f00"),  # orange
        ("cc7f00ff", "337f00ff"),  # violet
        ("cc00a5ff", "3300a5ff"),  # sky
    ]

    parts = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
    parts.append("<Document>")
    parts.append("<name>Scene Footprints (Observation corners)</name>")
    doc_desc = "Polygons generated from Observation* corner coordinates (UL/UR/LR/LL). WGS84 lon/lat."
    parts.append(f"<description>{escape(doc_desc)}</description>")

    for i, (line_color, poly_color) in enumerate(style_colors, start=1):
        parts.append(f'<Style id="style{i}">')
        parts.append(f'  <LineStyle><color>{line_color}</color><width>2</width></LineStyle>')
        parts.append(f'  <PolyStyle><color>{poly_color}</color><fill>1</fill><outline>1</outline></PolyStyle>')
        parts.append('</Style>')

    for idx, r in enumerate(records):
        style_id = f"style{(idx % len(style_colors)) + 1}"
        name = f"Scene {r['label']}" if r["label"] is not None else os.path.basename(r["filepath"])
        desc = escape(f"Label: {r['label']}\nProductID: {r['product_id']}\nFile: {os.path.basename(r['filepath'])}")

        # KML座標: lon,lat,0 をスペース区切りで（最後はリングを閉じる点）
        coords_str = " ".join([f"{lon:.8f},{lat:.8f},0" for lon, lat in zip(r["lons"], r["lats"])])

        parts.append("<Placemark>")
        parts.append(f"<name>{escape(name)}</name>")
        parts.append(f"<styleUrl>#{style_id}</styleUrl>")
        parts.append(f"<description>{desc}</description>")
        parts.append("<Polygon>")
        parts.append("<tessellate>1</tessellate>")
        parts.append("<outerBoundaryIs><LinearRing><coordinates>")
        parts.append(coords_str)
        parts.append("</coordinates></LinearRing></outerBoundaryIs>")
        parts.append("</Polygon>")
        parts.append("</Placemark>")

        # 中心点に番号ラベル
        label_text = str(r["label"]) if r["label"] is not None else "?"
        parts.append("<Placemark>")
        parts.append(f"<name>{escape(label_text)}</name>")
        parts.append(f"<styleUrl>#{style_id}</styleUrl>")
        parts.append(f"<description>{desc}</description>")
        parts.append("<Point><coordinates>")
        parts.append(f"{r['cx']:.8f},{r['cy']:.8f},0")
        parts.append("</coordinates></Point>")
        parts.append("</Placemark>")

    parts.append("</Document></kml>")

    with open(out_kml, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"[OK] KML saved: {out_kml}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", required=True, help="TXTが入ったフォルダ")
    ap.add_argument("--outkml", default=None, help="出力KMLパス（省略時は indir\\footprints_observation.kml）")
    args = ap.parse_args()

    out_kml = args.outkml or os.path.join(args.indir, "footprints_observation.kml")

    recs = collect_records(args.indir)
    if not recs:
        raise SystemExit("No valid TXT files found or missing Observation* keys.")
    write_kml(recs, out_kml)

if __name__ == "__main__":
    main()
