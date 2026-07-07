# -*- coding: utf-8 -*-
"""
MODTRAN water table builder (pandas-old-compatible)
- Reads files: ch_h2ostr_0.00_scan.csv ... ch_h2ostr_7.50_scan.csv
- From row 7 onward (Excel counting), take col-1 (wavelength) and col-10 (total)
- Output: modtranwaterdata_full.csv with columns: waveln, 0.00, 0.25, ..., 7.50
"""
import numpy as np

import os
import re
import sys
from glob import glob
from typing import List, Tuple
import inspect

import pandas as pd

# ====== 設定 ======
INPUT_DIR = r"E:\メタン\2025_HISUI_1_地獄の門\MOD\WATER" # ← ログに合わせてここを変更
OUTPUT_CSV = os.path.join(INPUT_DIR, "modtranwaterdata_full.csv")

FILE_PREFIX = "ch_h2ostr_"
FILE_SUFFIX = "_scan.csv"

# Excelの行・列番号（1始まり）
START_ROW_EXCEL = 7      # 7行目から
WAVEL_COL_EXCEL = 1      # 1列目: waveln
TOTAL_COL_EXCEL = 10     # 10列目: total

# 0.00〜7.50の0.25刻み
EXPECTED_VALUES = [f"{i/100:.2f}" for i in range(0, 501, 25)]
# ===================

def list_expected_files(input_dir: str) -> List[Tuple[str, str]]:
    out = []
    for s in EXPECTED_VALUES:
        fn = f"{FILE_PREFIX}{s}{FILE_SUFFIX}"
        out.append((s, os.path.join(input_dir, fn)))
    return out

def robust_read_csv(path: str, skiprows: int, wl_idx0: int, total_idx0: int) -> pd.DataFrame:
    """
    古い/新しい pandas 双方で動くように、on_bad_lines or error_bad_lines を自動選択。
    区切りは自動判定（engine='python', sep=None）。
    """
    # on_bad_lines が使えるかどうかを事前判定
    sig = inspect.signature(pd.read_csv)
    supports_on_bad_lines = "on_bad_lines" in sig.parameters

    encodings = ("utf-8-sig", "cp932", "utf-8", "latin-1")
    last_err = None
    for enc in encodings:
        try:
            kwargs = dict(
                header=None,
                skiprows=skiprows,
                encoding=enc,
                engine="python",
                sep=None,  # 区切り自動推定
            )
            if supports_on_bad_lines:
                kwargs["on_bad_lines"] = "skip"
            else:
                # 古いpandas向け（将来のpandasでは無視される）
                kwargs["error_bad_lines"] = False
                kwargs["warn_bad_lines"] = False

            df = pd.read_csv(path, **kwargs)

            if df.shape[1] <= max(wl_idx0, total_idx0):
                raise ValueError(f"{os.path.basename(path)} has only {df.shape[1]} columns (need >= {max(wl_idx0, total_idx0)+1}).")

            sub = df.iloc[:, [wl_idx0, total_idx0]].copy()
            sub.columns = ["waveln", "total"]
            sub["waveln"] = pd.to_numeric(sub["waveln"], errors="coerce")
            sub["total"]  = pd.to_numeric(sub["total"],  errors="coerce")
            sub = sub.dropna(subset=["waveln"]).reset_index(drop=True)
            return sub
        except Exception as e:
            last_err = e
    raise last_err if last_err else RuntimeError(f"Unable to read {path}")

def main():
    skiprows = START_ROW_EXCEL - 1
    wl_idx0 = WAVEL_COL_EXCEL - 1
    total_idx0 = TOTAL_COL_EXCEL - 1

    if not os.path.isdir(INPUT_DIR):
        print(f"[ERROR] INPUT_DIR does not exist: {INPUT_DIR}")
        sys.exit(1)

    plan = list_expected_files(INPUT_DIR)

    pattern = os.path.join(INPUT_DIR, f"{FILE_PREFIX}*{FILE_SUFFIX}")
    found_any = glob(pattern)
    print(f"[INFO] Found files matching pattern: {len(found_any)}")
    for demo in sorted(found_any)[:10]:
        print("   ", demo)

    master = None
    present_cols = []
    missing = []

    for colname, path in plan:
        if not os.path.isfile(path):
            missing.append(colname)
            continue
        try:
            sub = robust_read_csv(path, skiprows, wl_idx0, total_idx0)
            sub = sub.rename(columns={"total": colname})
            if master is None:
                master = sub
            else:
                master = master.merge(sub[["waveln", colname]], on="waveln", how="outer")
            present_cols.append(colname)
            print(f"[OK] {os.path.basename(path)} -> column '{colname}' rows={len(sub)}")
        except Exception as e:
            print(f"[FAIL] {os.path.basename(path)} ({e})")
            missing.append(colname)

    if master is None:
        print("[ERROR] No files were read successfully. Abort.")
        sys.exit(2)

    master = master.sort_values("waveln").reset_index(drop=True)
    desired_order = ["waveln"] + EXPECTED_VALUES
    for c in EXPECTED_VALUES:
        if c not in master.columns:
            master[c] = np.nan
    master = master[desired_order]

    master.to_csv(OUTPUT_CSV, index=False)
    print(f"[DONE] Wrote: {OUTPUT_CSV}")
    print(f"       rows={len(master)}  present_cols={len(present_cols)}  missing={len(missing)}")
    if missing:
        print("[WARN] Missing columns (files not found or failed to read):", ", ".join(missing))

if __name__ == "__main__":
    main()
