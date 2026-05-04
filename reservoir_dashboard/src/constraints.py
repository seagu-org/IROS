from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import normalize_key


VIOLATION_COLUMNS = [
    "datetime",
    "reservoir_name_en",
    "active_window_end_datetime",
    "season",
    "constraint_type",
    "violation_type",
    "simulated_water_level_m",
    "level_min_m",
    "level_max_m",
    "exceedance_m",
    "article_ref",
]


def datetime_to_mmdd(dt):
    ts = pd.to_datetime(dt)
    return int(ts.month * 100 + ts.day)


def is_mmdd_in_period(mmdd, start_mmdd, end_mmdd):
    if pd.isna(mmdd) or pd.isna(start_mmdd) or pd.isna(end_mmdd):
        return False
    mmdd = int(mmdd)
    start_mmdd = int(start_mmdd)
    end_mmdd = int(end_mmdd)
    if start_mmdd <= end_mmdd:
        return start_mmdd <= mmdd <= end_mmdd
    return mmdd >= start_mmdd or mmdd <= end_mmdd


def get_window_end_datetime(sim_df_or_obs_df):
    if sim_df_or_obs_df is None or sim_df_or_obs_df.empty or "datetime" not in sim_df_or_obs_df.columns:
        return pd.NaT
    values = pd.to_datetime(sim_df_or_obs_df["datetime"], errors="coerce").dropna()
    if values.empty:
        return pd.NaT
    return values.max()


def _mode_to_season(selected_mode):
    key = normalize_key(selected_mode)
    if key == "floodseason":
        return "flood_season"
    if key == "dryseason":
        return "dry_season"
    return None


def get_active_constraints_for_window_end(level_constraints_df, reservoir_name_en, window_end_datetime, selected_mode="Auto"):
    if level_constraints_df is None or level_constraints_df.empty or pd.isna(window_end_datetime):
        return pd.DataFrame(columns=["regulation_id", "reservoir_name_en", "season", "period_start_mmdd", "period_end_mmdd", "constraint_type", "level_min_m", "level_max_m", "article_ref"])
    df = level_constraints_df.copy()
    df = df[df["reservoir_name_en"].astype(str).map(normalize_key) == normalize_key(reservoir_name_en)]
    mmdd = datetime_to_mmdd(window_end_datetime)
    active = df[df.apply(lambda r: is_mmdd_in_period(mmdd, r.get("period_start_mmdd"), r.get("period_end_mmdd")), axis=1)].copy()
    season = _mode_to_season(selected_mode)
    if season:
        active = active[active["season"].astype(str).str.lower() == season]
    return active.reset_index(drop=True)


def _first_non_null(values):
    clean = [str(v) for v in values if pd.notna(v) and str(v).strip()]
    return "; ".join(dict.fromkeys(clean))


def aggregate_active_constraints(active_constraints_df):
    cols = ["reservoir_name_en", "season", "constraint_type", "level_min_m", "level_max_m", "article_ref"]
    if active_constraints_df is None or active_constraints_df.empty:
        return pd.DataFrame(columns=cols)
    df = active_constraints_df.copy()
    df["level_min_m"] = pd.to_numeric(df["level_min_m"], errors="coerce")
    df["level_max_m"] = pd.to_numeric(df["level_max_m"], errors="coerce")
    df = df[df["level_min_m"].notna() | df["level_max_m"].notna()]
    if df.empty:
        return pd.DataFrame(columns=cols)
    grouped = df.groupby(["reservoir_name_en", "season", "constraint_type"], dropna=False).agg(
        level_min_m=("level_min_m", lambda s: s.dropna().min() if s.dropna().size else np.nan),
        level_max_m=("level_max_m", lambda s: s.dropna().max() if s.dropna().size else np.nan),
        article_ref=("article_ref", _first_non_null),
    )
    return grouped.reset_index()[cols]


def build_constraint_plot_series(sim_df, aggregated_constraints_df):
    cols = ["datetime", "constraint_label", "constraint_level_m", "season", "constraint_type", "bound_type", "article_ref"]
    if sim_df is None or sim_df.empty or aggregated_constraints_df is None or aggregated_constraints_df.empty:
        return pd.DataFrame(columns=cols)
    datetimes = pd.to_datetime(sim_df["datetime"], errors="coerce").dropna().sort_values().unique()
    rows = []
    for _, c in aggregated_constraints_df.iterrows():
        for bound_col, bound_type in [("level_min_m", "min"), ("level_max_m", "max")]:
            level = c.get(bound_col)
            if pd.isna(level):
                continue
            label = f"{c['constraint_type']}_{bound_type}"
            for dt in datetimes:
                rows.append({
                    "datetime": dt,
                    "constraint_label": label,
                    "constraint_level_m": float(level),
                    "season": c.get("season"),
                    "constraint_type": c.get("constraint_type"),
                    "bound_type": bound_type,
                    "article_ref": c.get("article_ref", ""),
                })
    return pd.DataFrame(rows, columns=cols)


def check_level_violations(sim_df, aggregated_constraints_df, reservoir_name_en, window_end_datetime):
    if sim_df is None or sim_df.empty or aggregated_constraints_df is None or aggregated_constraints_df.empty:
        return pd.DataFrame(columns=VIOLATION_COLUMNS)
    rows = []
    for _, sim in sim_df.iterrows():
        level = sim.get("water_level_m")
        if pd.isna(level):
            continue
        for _, c in aggregated_constraints_df.iterrows():
            min_level = c.get("level_min_m")
            max_level = c.get("level_max_m")
            if pd.notna(min_level) and level < min_level:
                rows.append({
                    "datetime": sim["datetime"],
                    "reservoir_name_en": reservoir_name_en,
                    "active_window_end_datetime": window_end_datetime,
                    "season": c.get("season"),
                    "constraint_type": c.get("constraint_type"),
                    "violation_type": "below_min",
                    "simulated_water_level_m": level,
                    "level_min_m": min_level,
                    "level_max_m": max_level,
                    "exceedance_m": min_level - level,
                    "article_ref": c.get("article_ref", ""),
                })
            if pd.notna(max_level) and level > max_level:
                rows.append({
                    "datetime": sim["datetime"],
                    "reservoir_name_en": reservoir_name_en,
                    "active_window_end_datetime": window_end_datetime,
                    "season": c.get("season"),
                    "constraint_type": c.get("constraint_type"),
                    "violation_type": "above_max",
                    "simulated_water_level_m": level,
                    "level_min_m": min_level,
                    "level_max_m": max_level,
                    "exceedance_m": level - max_level,
                    "article_ref": c.get("article_ref", ""),
                })
    return pd.DataFrame(rows, columns=VIOLATION_COLUMNS)
