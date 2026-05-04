from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import calculate_end_of_window_capacity_metrics


def _scenario_frame(obs_df, values, name):
    return pd.DataFrame({
        "datetime": pd.to_datetime(obs_df["datetime"]),
        "outflow_m3s": pd.to_numeric(values, errors="coerce"),
        "scenario_name": name,
    })


def make_default_outflow(obs_df):
    return _scenario_frame(obs_df, obs_df["outflow_m3s"], "default_outflow")


def make_constant_outflow(obs_df, value_m3s):
    return _scenario_frame(obs_df, float(value_m3s), "constant_outflow")


def make_multiplier_outflow(obs_df, multiplier):
    return _scenario_frame(obs_df, pd.to_numeric(obs_df["outflow_m3s"], errors="coerce") * float(multiplier), f"multiplier_{float(multiplier):g}")


def make_time_window_outflow(obs_df, start, end, value_m3s):
    out = pd.to_numeric(obs_df["outflow_m3s"], errors="coerce").copy()
    dt = pd.to_datetime(obs_df["datetime"])
    mask = (dt >= pd.to_datetime(start)) & (dt <= pd.to_datetime(end))
    out.loc[mask] = float(value_m3s)
    return _scenario_frame(obs_df, out, "time_window_adjustment")


def make_manual_outflow(edited_df):
    df = edited_df.copy()
    if "scenario_name" not in df.columns:
        df["scenario_name"] = "manual_outflow"
    return df[["datetime", "outflow_m3s", "scenario_name"]].copy()


def compare_scenarios(results_dict, aggregated_constraints_df, capacity_targets):
    rows = []
    for scenario_name, payload in results_dict.items():
        sim_df = payload["simulation"] if isinstance(payload, dict) else payload
        obs_df = payload.get("obs_df") if isinstance(payload, dict) else None
        metrics = calculate_end_of_window_capacity_metrics(sim_df, obs_df if obs_df is not None else sim_df, capacity_targets, None)
        target = capacity_targets.get("capacity_target_m3", np.nan) if capacity_targets else np.nan
        rows.append({
            "scenario_name": scenario_name,
            "max_water_level_m": sim_df["water_level_m"].max(),
            "min_water_level_m": sim_df["water_level_m"].min(),
            "final_water_level_m": sim_df["water_level_m"].iloc[-1],
            "max_storage_m3": sim_df["storage_m3"].max(),
            "final_storage_m3": sim_df["storage_m3"].iloc[-1],
            "physical_limit_violation_count": metrics.get("physical_limit_violation_count", 0),
            "max_physical_limit_excess_mcm": metrics.get("max_physical_limit_excess_mcm", np.nan),
            "capacity_target_type": capacity_targets.get("capacity_target_type", "unavailable") if capacity_targets else "unavailable",
            "capacity_target_m3": target,
            "max_capacity_used_pct": sim_df["storage_m3"].max() / target * 100 if pd.notna(target) and target else np.nan,
            "final_capacity_used_pct": metrics.get("capacity_used_pct", np.nan),
            "remaining_storage_m3": metrics.get("remaining_storage_m3", np.nan),
            "remaining_storage_mcm": metrics.get("remaining_storage_mcm", np.nan),
            "remaining_pct": metrics.get("remaining_pct", np.nan),
            "hours_to_fill_from_average_inflow": metrics.get("hours_to_fill_from_inflow_only", np.nan),
            "days_to_fill_from_average_inflow": metrics.get("days_to_fill_from_inflow_only", np.nan),
        })
    return pd.DataFrame(rows)
