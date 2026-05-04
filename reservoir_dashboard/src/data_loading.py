from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .excel_conversion import clean_reservoir_name_for_filename
from .reservoir_model import prepare_hypsometry
from .utils import normalize_key


def match_reservoir_name(name, candidates):
    candidates = list(candidates)
    if name in candidates:
        return name
    target = normalize_key(name)
    for candidate in candidates:
        if normalize_key(candidate) == target:
            return candidate
    return None


def load_reservoir_ids(path):
    df = pd.read_csv(path)
    if "reservoir_name_en" not in df.columns:
        raise ValueError("reservoir_id.csv must include reservoir_name_en")
    return df


def load_reservoir_parameters(path):
    df = pd.read_csv(path)
    if "reservoir_name_en" in df.columns:
        df["reservoir_name_en"] = df["reservoir_name_en"].astype(str).str.strip()
    if "value" in df.columns:
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def load_level_constraints(path):
    df = pd.read_csv(path)
    keep = ["regulation_id", "reservoir_name_en", "season", "period_start_mmdd", "period_end_mmdd", "constraint_type", "level_min_m", "level_max_m", "article_ref"]
    for col in keep:
        if col not in df.columns:
            df[col] = np.nan
    df = df[keep].copy()
    for col in ["period_start_mmdd", "period_end_mmdd", "level_min_m", "level_max_m"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["season"] = df["season"].astype(str).str.strip().str.lower()
    return df


def _read_aev_file(path):
    try:
        return pd.read_csv(path, sep=None, engine="python")
    except Exception:
        return pd.read_csv(path, sep="\t")


def load_hypsometry(aev_path, selected_reservoir):
    path = Path(aev_path)
    if path.is_dir():
        files = list(path.glob("*"))
        matched = None
        for candidate in files:
            if candidate.is_file() and normalize_key(candidate.stem) == normalize_key(selected_reservoir):
                matched = candidate
                break
        if matched is None:
            return pd.DataFrame(), None
        df = _read_aev_file(matched)
        source = matched
    else:
        df = _read_aev_file(path)
        source = path
        name_cols = [c for c in df.columns if "reservoir" in normalize_key(c) or "tenho" in normalize_key(c)]
        if name_cols:
            col = name_cols[0]
            df = df[df[col].astype(str).map(normalize_key) == normalize_key(selected_reservoir)]
    return prepare_hypsometry(df), source


def load_clean_observed_timeseries(csv_folder, selected_reservoir):
    folder = Path(csv_folder)
    if not folder.exists():
        return pd.DataFrame(), None
    files = list(folder.glob("*.csv"))
    matched = None
    for path in files:
        if normalize_key(path.stem) == normalize_key(clean_reservoir_name_for_filename(selected_reservoir)):
            matched = path
            break
    if matched is None:
        return pd.DataFrame(), None
    df = pd.read_csv(matched)
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    for col in ["inflow_m3s", "outflow_m3s", "water_level_m"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True), matched


def clean_observed_timeseries_dataframe(df, selected_reservoir):
    out = df.copy()
    required = ["datetime", "inflow_m3s", "outflow_m3s"]
    missing = [col for col in required if col not in out.columns]
    if missing:
        raise ValueError("Observed CSV must include columns: " + ", ".join(required))
    if "reservoir_name_en" not in out.columns:
        out["reservoir_name_en"] = selected_reservoir
    if "water_level_m" not in out.columns:
        out["water_level_m"] = np.nan
    out["datetime"] = pd.to_datetime(out["datetime"], errors="coerce")
    for col in ["inflow_m3s", "outflow_m3s", "water_level_m"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)


def load_uploaded_observed_timeseries(file_obj, selected_reservoir):
    df = pd.read_csv(file_obj)
    return clean_observed_timeseries_dataframe(df, selected_reservoir)


def filter_time_window(obs_df, start_datetime, window_option, custom_end_datetime=None):
    if obs_df is None or obs_df.empty:
        return pd.DataFrame()
    start = pd.to_datetime(start_datetime)
    if window_option == "24 hours":
        end = start + pd.Timedelta(hours=24)
    elif window_option == "48 hours":
        end = start + pd.Timedelta(hours=48)
    elif window_option == "72 hours":
        end = start + pd.Timedelta(hours=72)
    elif window_option == "1 week":
        end = start + pd.Timedelta(days=7)
    elif window_option == "2 weeks":
        end = start + pd.Timedelta(days=14)
    else:
        end = pd.to_datetime(custom_end_datetime)
    df = obs_df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    return df[(df["datetime"] >= start) & (df["datetime"] <= end)].sort_values("datetime").reset_index(drop=True)


def get_initial_water_level(obs_df):
    if obs_df is None or obs_df.empty:
        return np.nan, pd.NaT, False
    df = obs_df.sort_values("datetime").reset_index(drop=True)
    valid_inflow = df[df["inflow_m3s"].notna()]
    if valid_inflow.empty:
        return np.nan, pd.NaT, False
    first = valid_inflow.iloc[0]
    if pd.notna(first.get("water_level_m")):
        return float(first["water_level_m"]), first["datetime"], True
    water = df[df["water_level_m"].notna()]
    if water.empty:
        return np.nan, first["datetime"], False
    idx = (pd.to_datetime(water["datetime"]) - pd.to_datetime(first["datetime"])).abs().idxmin()
    return float(water.loc[idx, "water_level_m"]), first["datetime"], False
