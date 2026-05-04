from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .utils import normalize_key, normalize_text


CLEAN_Q_COLUMNS = [
    "datetime",
    "date",
    "hour",
    "reservoir_name_en",
    "inflow_m3s",
    "outflow_m3s",
    "water_level_m",
]


ALIASES = {
    "date": ["ngay", "date"],
    "hour": ["gio", "hour"],
    "inflow_m3s": ["luuluongdenho", "inflowm3s", "inflow"],
    "outflow_m3s": ["tongluuluongxa", "outflowm3s", "outflow"],
    "water_level_m": ["mucnuocho", "waterlevelm", "waterlevel"],
}


def clean_reservoir_name_for_filename(name):
    text = normalize_text(name)
    return re.sub(r"\s+", " ", text).strip()


def parse_vietnamese_number(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "tb"}:
        return np.nan
    text = text.replace("\u00a0", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    text = re.sub(r"[^0-9eE+\-.]", "", text)
    if text in {"", ".", "-", "+"}:
        return np.nan
    try:
        return float(text)
    except ValueError:
        return np.nan


def parse_hour_value(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    if isinstance(value, pd.Timestamp):
        return int(value.hour)
    if hasattr(value, "hour") and not isinstance(value, (int, float, str)):
        return int(value.hour)
    if isinstance(value, (int, float, np.integer, np.floating)):
        if np.isnan(value):
            return np.nan
        hour = int(value)
        return hour if 0 <= hour <= 23 else np.nan
    text = normalize_text(value).lower()
    if not text or "tb" in text:
        return np.nan
    match = re.search(r"(\d{1,2})", text)
    if not match:
        return np.nan
    hour = int(match.group(1))
    return hour if 0 <= hour <= 23 else np.nan


def _find_header_row(raw_df: pd.DataFrame) -> int:
    best_idx = 0
    best_score = -1
    alias_keys = {alias for aliases in ALIASES.values() for alias in aliases}
    for idx, row in raw_df.head(30).iterrows():
        keys = [normalize_key(v) for v in row.tolist()]
        score = sum(any(alias in key for alias in alias_keys) for key in keys)
        if score > best_score:
            best_idx = idx
            best_score = score
    return int(best_idx)


def _rename_required_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = {}
    normalized_columns = {col: normalize_key(col) for col in df.columns}
    for target, aliases in ALIASES.items():
        for col, key in normalized_columns.items():
            if key == target or any(alias in key for alias in aliases):
                renamed[col] = target
                break
    return df.rename(columns=renamed)


def read_reservoir_excel(path, reservoir_name_en):
    path = Path(path)
    raw = pd.read_excel(path, header=None, engine="openpyxl")
    header_idx = _find_header_row(raw)
    df = pd.read_excel(path, header=header_idx, engine="openpyxl")
    return clean_reservoir_q_dataframe(df, reservoir_name_en)


def clean_reservoir_q_dataframe(df, reservoir_name_en):
    df = _rename_required_columns(df.copy())
    missing = [col for col in ["date", "hour", "inflow_m3s", "outflow_m3s", "water_level_m"] if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required Q columns: {missing}")

    df = df[["date", "hour", "inflow_m3s", "outflow_m3s", "water_level_m"]].copy()
    hour_text = df["hour"].astype(str)
    df = df[~hour_text.str.contains("TB", case=False, na=False)].copy()
    df["hour"] = df["hour"].map(parse_hour_value)
    df = df[df["hour"].notna()].copy()
    df["hour"] = df["hour"].astype(int)

    parsed_date = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df["datetime"] = parsed_date + pd.to_timedelta(df["hour"], unit="h")
    for col in ["inflow_m3s", "outflow_m3s", "water_level_m"]:
        df[col] = df[col].map(parse_vietnamese_number)

    df["date"] = df["datetime"].dt.date.astype(str)
    df["reservoir_name_en"] = reservoir_name_en
    df = df.dropna(subset=["datetime"]).sort_values("datetime")
    return df[CLEAN_Q_COLUMNS].reset_index(drop=True)


def find_excel_for_reservoir(input_folder, reservoir_name_en):
    folder = Path(input_folder)
    if not folder.exists():
        return None
    expected = folder / f"{reservoir_name_en}.xlsx"
    if expected.exists():
        return expected
    candidates = list(folder.glob("*.xlsx"))
    target_clean = clean_reservoir_name_for_filename(reservoir_name_en)
    target_key = normalize_key(target_clean)
    for path in candidates:
        if normalize_key(path.stem) == target_key:
            return path
    for path in candidates:
        if normalize_key(clean_reservoir_name_for_filename(path.stem)) == target_key:
            return path
    return None


def convert_all_q_excel_to_csv(input_folder, output_folder, reservoir_ids_df):
    output = Path(output_folder)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in reservoir_ids_df["reservoir_name_en"].dropna().astype(str):
        excel_path = find_excel_for_reservoir(input_folder, name)
        if excel_path is None:
            rows.append({"reservoir_name_en": name, "status": "missing_excel", "rows": 0, "csv_path": ""})
            continue
        try:
            clean = read_reservoir_excel(excel_path, name)
            csv_path = output / f"{clean_reservoir_name_for_filename(name)}.csv"
            clean.to_csv(csv_path, index=False)
            rows.append({"reservoir_name_en": name, "status": "converted", "rows": len(clean), "csv_path": str(csv_path)})
        except Exception as exc:
            rows.append({"reservoir_name_en": name, "status": f"error: {exc}", "rows": 0, "csv_path": ""})
    return pd.DataFrame(rows)
