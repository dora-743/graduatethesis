# -*- coding: utf-8 -*-
"""
CH4.csv 作成スクリプト（完成版）

- 探索フォルダ内の「末尾が scan.csv」のファイルを対象
- ファイル名中の "h2ostr_数値"（例: ch_h2ostr_3.30_scan.csv）から数値を抽出し、列名に利用
- 各CSVの 10 列目（0始まり index=9）を横に結合
- 1列目は最初のファイルの1列目（数値）を採用（数値でない場合は行番号）
- 先頭に長い説明ヘッダがあっても、最初の「数値行」から読み込み開始
- 区切りは基本カンマ想定。うまく行かない場合は混在区切り（, / \t / ; / 2+空白）で再読込
- 文字コードは utf-8[-sig]/cp932/utf-16 を順にトライ

出力: E:\refit\CH4.csv
"""

from pathlib import Path
from typing import List, Tuple, Optional, Union, Dict
import re
import pandas as pd
import numpy as np
from collections import defaultdict


# ===================== 設定 =====================
DIRS_IN: List[Path] = [
    Path(r"E:\tools\thesis\16genkai\out_prof_ch4"),  # 必要に応じて追加・変更
    # Path(r"E:\refit\h2o_2\out_prof_ch4_alt"),
]
RECURSIVE: bool = False                  # 下位フォルダも探索する場合 True
SUFFIX: str = "scan.csv"                 # 末尾がこれのファイルのみ対象（大文字小文字無視）
TARGET_COL_IDX: int = 9                  # 10 列目（0始まり index=9）
FILE_OUT: Path = Path(r"E:\tools\thesis\16genkai\lutall.csv")
INDEX_COL_NAME: str = "Waveln"                # 出力の1列目の見出し（例: "Wavelength_nm" に変更可）
# ==============================================


def extract_value_from_name(name: str) -> Optional[float]:
    """
    ファイル名から h2ostr_数値 を抽出。揺れに強い2段構え。
    """
    patterns = [
        re.compile(r"(?i)h2ostr[\-_]*([+-]?\d+(?:\.\d+)?)(?=[^\d]*_scan\.csv$)"),
        re.compile(r"([+-]?\d+(?:\.\d+)?)(?=[^\d]*_scan\.csv$)", re.IGNORECASE),
    ]
    for pat in patterns:
        m = pat.search(name)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
    return None


def _read_csv_try_encodings(path: Path, **kwargs) -> pd.DataFrame:
    """
    いくつかのエンコーディングで順に read_csv を試す。
    """
    encs = ["utf-8-sig", "utf-8", "cp932", "utf-16"]
    last_err = None
    for enc in encs:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except UnicodeDecodeError as e:
            last_err = e
            continue
    # 最後の手
    if last_err:
        # encoding 指定なしでチャレンジ
        return pd.read_csv(path, **kwargs)
    return pd.read_csv(path, **kwargs)


def _read_ch4_csv(path: Path, target_col_idx: int) -> pd.DataFrame:
    """
    MODTRAN系のように冒頭に説明ブロックがあるCSVに対応。
    1) 先頭フィールドが「数値」の最初の行を検出 → skiprows に設定
    2) まずはカンマ区切りで読込
    3) 列不足なら混在区切り（, / tab / ; / 2+空白）で再読込
    """
    try:
        raw_lines = path.read_text(errors="ignore").splitlines()
    except Exception:
        # 読み取りに失敗したらエンコーディング指定で再読
        raw_lines = _read_csv_try_encodings(path, header=None).to_string().splitlines()

    num_pat = re.compile(r"^[\s]*[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\s*$")

    start = None
    for i, line in enumerate(raw_lines):
        # カンマ前提で先頭フィールドを抜く
        first = line.split(",")[0]
        if num_pat.match(first):
            start = i
            break
    if start is None:
        # 空白分割でも試す
        for i, line in enumerate(raw_lines):
            first = re.split(r"\s+", line.strip())[0] if line.strip() else ""
            if num_pat.match(first):
                start = i
                break
    if start is None:
        raise ValueError(f"数値データ開始行を検出できませんでした: {path.name}")

    # まずカンマ区切りで
    df = _read_csv_try_encodings(path, header=None, skiprows=start, engine="python")
    if df.shape[1] <= target_col_idx:
        # 列が足りない → 区切り混在として再試行
        df = _read_csv_try_encodings(
            path,
            header=None,
            skiprows=start,
            sep=r"[,\t;]|[ ]{2,}",
            engine="python",
        )

    if df.shape[1] <= target_col_idx:
        raise ValueError(f"{path.name} に {target_col_idx+1} 列目がありません（列数={df.shape[1]}）。")

    return df


def iter_candidate_files(roots: List[Path], suffix: str, recursive: bool):
    """
    末尾が suffix（例: 'scan.csv'）のファイルを列挙（大文字小文字無視）。
    """
    suffix_lower = suffix.lower()
    for root in roots:
        if recursive:
            it = root.rglob(f"*{suffix}")
        else:
            it = root.glob(f"*{suffix}")
        for p in it:
            if p.name.lower().endswith(suffix_lower):
                yield p


def main():
    # ------- 入力ファイル収集 -------
    candidates: List[Tuple[Union[float, Tuple[float, str]], Path]] = []
    skipped: List[str] = []

    for p in iter_candidate_files(DIRS_IN, SUFFIX, RECURSIVE):
        val = extract_value_from_name(p.name)
        if val is None:
            skipped.append(p.name)
        else:
            candidates.append((val, p))

    if not candidates:
        raise FileNotFoundError(
            "対象ファイルが見つかりませんでした。\n"
            f"探索フォルダ: {[str(d) for d in DIRS_IN]}\n"
            f"条件: 末尾が '{SUFFIX}' かつ ファイル名内に 'h2ostr_数値'（例: ch_h2ostr_0.00_scan.csv）"
        )

    # 値が同じファイル（例: 0.00 が複数）に a,b,c…を付けて列名衝突回避
    groups: Dict[float, List[Path]] = defaultdict(list)
    for v, p in candidates:
        groups[v].append(p)

    resolved: List[Tuple[Union[float, Tuple[float, str]], Path]] = []
    for v, paths in groups.items():
        if len(paths) == 1:
            resolved.append((v, paths[0]))
        else:
            for i, p in enumerate(sorted(paths)):
                tag = chr(ord("a") + i)  # a, b, c...
                resolved.append(((v, tag), p))

    def sort_key(item):
        v, _p = item
        if isinstance(v, tuple):
            return (v[0], v[1])
        return (v, "")

    resolved.sort(key=sort_key)

    print(f"探索ヒット: {len(resolved)} 件")
    if skipped:
        print(f"値抽出できずスキップ: {len(skipped)} 件（例）→ {skipped[:5]}")

    # ------- 読み込み & 集約 -------
    series_dict: Dict[str, pd.Series] = {}
    index_col: Optional[pd.Series] = None

    for idx, (valkey, path) in enumerate(resolved):
        df = _read_ch4_csv(path, TARGET_COL_IDX)

        # 10列目（index=9）
        s = pd.to_numeric(df.iloc[:, TARGET_COL_IDX], errors="coerce").reset_index(drop=True)

        # 1列目は最初のファイルの1列目（数値）を採用。数値で無ければ行番号。
        if idx == 0:
            idx_candidate = pd.to_numeric(df.iloc[:, 0], errors="coerce")
            if idx_candidate.notna().any():
                index_col = idx_candidate.reset_index(drop=True)
            else:
                index_col = pd.Series(np.arange(len(s)), name=INDEX_COL_NAME)

        # 長さを最長に合わせてパディング
        assert index_col is not None
        max_len = max(len(index_col), *(len(v) for v in series_dict.values())) if series_dict else max(len(index_col), len(s))

        def pad_to(series: pd.Series, length: int) -> pd.Series:
            if len(series) < length:
                return series.reindex(range(length))
            return series

        s = pad_to(s, max_len)
        index_col = pad_to(index_col, max_len)
        for k in list(series_dict.keys()):
            series_dict[k] = pad_to(series_dict[k], max_len)

        # 列名を作成（重複値は a,b…付き）
        if isinstance(valkey, tuple):
            v, tag = valkey
            col_name = f"{v:.2f}{tag}"
        else:
            col_name = f"{valkey:.2f}"

        series_dict[col_name] = s

    # ------- 出力 -------
    out = pd.DataFrame({INDEX_COL_NAME: index_col})
    # 列は数値→サフィックスの順で安定ソート
    def col_sort_key(x: str):
        m = re.match(r"^([+-]?\d+(?:\.\d+)?)([a-z]?)$", x)
        if m:
            return (float(m.group(1)), m.group(2))
        return (float("inf"), x)

    for col in sorted(series_dict.keys(), key=col_sort_key):
        out[col] = series_dict[col].values

    FILE_OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(FILE_OUT, index=False, encoding="utf-8-sig")

    print(f"作成しました: {FILE_OUT}")
    print(f"形状: {out.shape[0]} 行 x {out.shape[1]} 列")
    print("列見出し（先頭10）:", list(out.columns)[:10])


if __name__ == "__main__":
    main()
