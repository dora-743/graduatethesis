# -*- coding: utf-8 -*-
# D:\normalize_bg_scans.py
# *_scan.csv を再整形して 2列 (wave_nm, radiance) のCSVを作る

import os, inspect
from glob import glob
import pandas as pd
import numpy as np

ROOT_DIR = r"E:\permian_basin\data_5\bg"   # ここを必要なら変更
OUT_DIR  = os.path.join(ROOT_DIR, "normalized")
START_ROW_EXCEL   = 7   # 7行目から（Excelの数え方）
WAVEL_COL_EXCEL   = 1   # 1列目（波長）
RADIANCE_COL_EXCEL= 10  # 10列目（放射輝度）

os.makedirs(OUT_DIR, exist_ok=True)

def supports_on_bad_lines() -> bool:
    return "on_bad_lines" in inspect.signature(pd.read_csv).parameters

def read_two_cols(path: str):
    skiprows = START_ROW_EXCEL - 1
    wl_idx0  = WAVEL_COL_EXCEL - 1
    rad_idx0 = RADIANCE_COL_EXCEL - 1
    encs = ("utf-8-sig","cp932","utf-8","latin-1")
    last_err = None
    for enc in encs:
        try:
            kwargs = dict(
                header=None,
                skiprows=skiprows,
                encoding=enc,
                engine="python",
                sep=None,  # 区切り自動判定（, / \t / ; など）
            )
            if supports_on_bad_lines():
                kwargs["on_bad_lines"] = "skip"
            else:
                kwargs["error_bad_lines"] = False  # type: ignore
                kwargs["warn_bad_lines"]  = False  # type: ignore

            df = pd.read_csv(path, **kwargs)
            if df.shape[1] <= max(wl_idx0, rad_idx0):
                raise ValueError(f"{os.path.basename(path)} has only {df.shape[1]} columns.")
            sub = df.iloc[:, [wl_idx0, rad_idx0]].copy()
            sub.columns = ["wave_nm", "radiance"]
            sub["wave_nm"] = pd.to_numeric(sub["wave_nm"], errors="coerce")
            sub["radiance"] = pd.to_numeric(sub["radiance"], errors="coerce")
            sub = sub.dropna(subset=["wave_nm"]).reset_index(drop=True)
            return sub
        except Exception as e:
            last_err = e
    raise last_err if last_err else RuntimeError(f"Failed to read {path}")

def main():
    # ルート直下とサブフォルダも検索：*_scan.csv
    pattern1 = os.path.join(ROOT_DIR, "*_scan.csv")
    pattern2 = os.path.join(ROOT_DIR, "**", "*_scan.csv")
    files = sorted(set(glob(pattern1)) | set(glob(pattern2, recursive=True)))
    print(f"[INFO] scan-files found: {len(files)}")

    if not files:
        print("[WARN] *_scan.csv が見つかりません。ROOT_DIR を確認してください。")
        return

    ok, fail = 0, 0
    for fp in files:
        try:
            sub = read_two_cols(fp)
            out_path = os.path.join(OUT_DIR, os.path.basename(fp))
            sub.to_csv(out_path, index=False)  # ヘッダ: wave_nm,radiance
            ok += 1
            print(f"[OK] {os.path.basename(fp)} -> {out_path}  rows={len(sub)}")
        except Exception as e:
            fail += 1
            print(f"[FAIL] {os.path.basename(fp)}  {e}")

    print(f"[DONE] normalized files: {ok}, failed: {fail}, out_dir: {OUT_DIR}")

if __name__ == "__main__":
    main()
