from __future__ import annotations

import numpy as np
import pandas as pd

from .reservoir_model import derive_capacity_from_level
from .reservoir_model import summarize_physical_limit_violations


STORAGE_PARAMETER_NAMES = {"dead_storage", "useful_storage", "total_storage_at_nwl", "annual_storage", "multi_year_storage"}


def _as_parameter_dict(reservoir_parameters):
    if reservoir_parameters is None:
        return {}
    if isinstance(reservoir_parameters, dict):
        return reservoir_parameters
    if isinstance(reservoir_parameters, pd.Series):
        return reservoir_parameters.to_dict()
    df = reservoir_parameters.copy()
    if {"parameter_name", "value"}.issubset(df.columns):
        return {str(r["parameter_name"]): r["value"] for _, r in df.iterrows()}
    if len(df) == 1:
        return df.iloc[0].to_dict()
    return {}


def _storage_value_m3(value, unit=None):
    if value is None or pd.isna(value):
        return np.nan
    value = float(value)
    unit_key = str(unit or "").lower()
    if "10^6" in unit_key or "million" in unit_key or "mcm" in unit_key:
        return value * 1e6
    if abs(value) < 10000:
        return value * 1e6
    return value


def _param_value(reservoir_parameters, name):
    if reservoir_parameters is None:
        return np.nan, None
    if isinstance(reservoir_parameters, pd.DataFrame) and {"parameter_name", "value"}.issubset(reservoir_parameters.columns):
        rows = reservoir_parameters[reservoir_parameters["parameter_name"].astype(str).str.lower() == name]
        if rows.empty:
            return np.nan, None
        row = rows.iloc[0]
        return pd.to_numeric(row.get("value"), errors="coerce"), row.get("unit")
    params = _as_parameter_dict(reservoir_parameters)
    return pd.to_numeric(params.get(name), errors="coerce"), params.get(f"{name}_unit")


def derive_reservoir_capacity_targets(reservoir_parameters, hypsometry_df, aggregated_constraints_df, active_season):
    targets = {}
    for level_name, target_name in [
        ("crest_elevation", "maximum_capacity_m3"),
        ("design_flood_level", "design_flood_level_capacity_m3"),
        ("flood_check_level", "flood_check_level_capacity_m3"),
        ("normal_water_level", "normal_water_level_capacity_m3"),
    ]:
        level, _ = _param_value(reservoir_parameters, level_name)
        targets[target_name] = derive_capacity_from_level(level, hypsometry_df) if pd.notna(level) else np.nan

    total_storage, total_unit = _param_value(reservoir_parameters, "total_storage_at_nwl")
    targets["total_storage_at_nwl_m3"] = _storage_value_m3(total_storage, total_unit) if pd.notna(total_storage) else targets.get("normal_water_level_capacity_m3", np.nan)
    targets["maximum_aev_volume_m3"] = float(hypsometry_df["volume_m3"].max()) if hypsometry_df is not None and not hypsometry_df.empty else np.nan

    candidates = []
    if active_season == "flood_season":
        candidates = [
            ("flood_check_level_capacity_m3", targets.get("flood_check_level_capacity_m3")),
            ("maximum_capacity_m3", targets.get("maximum_capacity_m3")),
            ("maximum_aev_volume_m3", targets.get("maximum_aev_volume_m3")),
        ]
    elif active_season == "dry_season":
        candidates = [
            ("total_storage_at_nwl_m3", targets.get("total_storage_at_nwl_m3")),
            ("normal_water_level_capacity_m3", targets.get("normal_water_level_capacity_m3")),
        ]
    else:
        candidates = [
            ("total_storage_at_nwl_m3", targets.get("total_storage_at_nwl_m3")),
            ("flood_check_level_capacity_m3", targets.get("flood_check_level_capacity_m3")),
            ("maximum_capacity_m3", targets.get("maximum_capacity_m3")),
            ("maximum_aev_volume_m3", targets.get("maximum_aev_volume_m3")),
        ]
    target_type, target_value = next(((name, value) for name, value in candidates if pd.notna(value) and value > 0), ("unavailable", np.nan))
    targets["capacity_target_type"] = target_type
    targets["capacity_target_m3"] = target_value
    return targets


def calculate_end_of_window_capacity_metrics(sim_df, obs_df, capacity_targets, active_season):
    if sim_df is None or sim_df.empty:
        return {}
    final = sim_df.sort_values("datetime").iloc[-1]
    target = capacity_targets.get("capacity_target_m3", np.nan) if capacity_targets else np.nan
    final_storage = final.get("storage_m3", np.nan)
    avg_inflow = pd.to_numeric(obs_df.get("inflow_m3s"), errors="coerce").mean() if obs_df is not None and "inflow_m3s" in obs_df else np.nan
    remaining = target - final_storage if pd.notna(target) and pd.notna(final_storage) else np.nan
    metrics = {
        "active_season": active_season,
        "capacity_target_type": capacity_targets.get("capacity_target_type", "unavailable") if capacity_targets else "unavailable",
        "capacity_target_m3": target,
        "capacity_used_pct": final_storage / target * 100 if pd.notna(target) and target else np.nan,
        "remaining_storage_m3": remaining,
        "remaining_storage_mcm": remaining / 1e6 if pd.notna(remaining) else np.nan,
        "remaining_pct": remaining / target * 100 if pd.notna(target) and target else np.nan,
        "avg_inflow_m3s": avg_inflow,
        "hours_to_fill_from_inflow_only": remaining / (avg_inflow * 3600) if pd.notna(remaining) and pd.notna(avg_inflow) and avg_inflow > 0 else np.nan,
        "days_to_fill_from_inflow_only": remaining / (avg_inflow * 3600 * 24) if pd.notna(remaining) and pd.notna(avg_inflow) and avg_inflow > 0 else np.nan,
    }
    metrics.update(summarize_physical_limit_violations(sim_df))
    return metrics
