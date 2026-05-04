from __future__ import annotations

import numpy as np
import pandas as pd


def prepare_hypsometry(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=["elevation_m", "area_km2", "area_m2", "volume_mcm", "volume_m3"])
    out = df.copy()
    rename = {
        "CaoTrinh_m": "elevation_m",
        "Dientich_km2": "area_km2",
        "Dungtich_10^6m3": "volume_mcm",
    }
    out = out.rename(columns=rename)
    needed = ["elevation_m", "area_km2", "volume_mcm"]
    for col in needed:
        if col not in out.columns:
            raise ValueError(f"Missing hypsometry column: {col}")
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["elevation_m", "volume_mcm"])
    out["area_m2"] = pd.to_numeric(out["area_km2"], errors="coerce") * 1e6
    out["volume_m3"] = out["volume_mcm"] * 1e6
    out = out.sort_values(["elevation_m", "volume_m3"])
    out = out.groupby("elevation_m", as_index=False).agg({"area_km2": "mean", "area_m2": "mean", "volume_mcm": "mean", "volume_m3": "mean"})
    out = out.sort_values(["volume_m3", "elevation_m"])
    out = out.groupby("volume_m3", as_index=False).agg({"elevation_m": "mean", "area_km2": "mean", "area_m2": "mean", "volume_mcm": "mean"})
    return out.sort_values("elevation_m").reset_index(drop=True)


def _interp(x, xp, fp):
    if pd.isna(x) or len(xp) == 0:
        return np.nan
    return float(np.interp(float(x), xp, fp))


def level_to_storage(level_m, hypsometry_df):
    h = prepare_hypsometry(hypsometry_df)
    return _interp(level_m, h["elevation_m"].to_numpy(), h["volume_m3"].to_numpy())


def storage_to_level(storage_m3, hypsometry_df):
    h = prepare_hypsometry(hypsometry_df).sort_values("volume_m3")
    return _interp(storage_m3, h["volume_m3"].to_numpy(), h["elevation_m"].to_numpy())


def storage_to_area(storage_m3, hypsometry_df):
    h = prepare_hypsometry(hypsometry_df).sort_values("volume_m3")
    return _interp(storage_m3, h["volume_m3"].to_numpy(), h["area_m2"].to_numpy())


def derive_capacity_from_level(level_m, hypsometry_df):
    if level_m is None or pd.isna(level_m):
        return np.nan
    return level_to_storage(level_m, hypsometry_df)


def summarize_physical_limit_violations(sim_df):
    if sim_df is None or sim_df.empty or "physical_limit_violation" not in sim_df:
        return {}
    violations = sim_df[sim_df["physical_limit_violation"].fillna(False)].copy()
    if violations.empty:
        return {}
    excess = pd.to_numeric(violations.get("physical_limit_excess_m3"), errors="coerce")
    types = sorted(violations.get("physical_limit_type", pd.Series(dtype=str)).dropna().astype(str).unique())
    return {
        "physical_limit_violation_count": int(len(violations)),
        "physical_limit_first_datetime": pd.to_datetime(violations["datetime"], errors="coerce").min(),
        "physical_limit_last_datetime": pd.to_datetime(violations["datetime"], errors="coerce").max(),
        "physical_limit_types": ", ".join(types),
        "max_physical_limit_excess_mcm": excess.max() / 1e6 if not excess.dropna().empty else np.nan,
    }


def simulate_reservoir(obs_df, scenario_outflow_df, initial_water_level_m, hypsometry_df, reservoir_parameters=None):
    obs = obs_df.copy().sort_values("datetime").reset_index(drop=True)
    out = scenario_outflow_df[["datetime", "outflow_m3s"]].copy()
    sim = obs.merge(out, on="datetime", how="left", suffixes=("_default", ""))
    if "outflow_m3s" not in sim.columns:
        sim["outflow_m3s"] = sim["outflow_m3s_default"]
    sim["outflow_m3s"] = sim["outflow_m3s"].fillna(sim.get("outflow_m3s_default"))
    scenario_name = scenario_outflow_df.get("scenario_name", pd.Series(["default_outflow"])).iloc[0]
    reservoir_name = obs["reservoir_name_en"].iloc[0] if "reservoir_name_en" in obs.columns and len(obs) else ""
    h = prepare_hypsometry(hypsometry_df)
    initial_storage = level_to_storage(initial_water_level_m, h)
    min_storage = h["volume_m3"].min()
    max_storage = h["volume_m3"].max()

    storages = []
    unbounded_storages = []
    levels = []
    areas = []
    physical_violations = []
    physical_violation_types = []
    physical_limit_excesses = []
    current = initial_storage
    prev_dt = None
    for _, row in sim.iterrows():
        dt = pd.to_datetime(row["datetime"])
        if prev_dt is None:
            dt_seconds = 0.0
        else:
            dt_seconds = max((dt - prev_dt).total_seconds(), 0.0)
            current = current + (row["inflow_m3s"] - row["outflow_m3s"]) * dt_seconds
        unbounded_current = current
        violation_type = ""
        excess = 0.0
        if pd.notna(unbounded_current) and unbounded_current < min_storage:
            excess = min_storage - unbounded_current
            current = min_storage
            violation_type = "below_min_storage"
        elif pd.notna(unbounded_current) and unbounded_current > max_storage:
            excess = unbounded_current - max_storage
            current = max_storage
            violation_type = "above_max_storage"
        storages.append(current)
        unbounded_storages.append(unbounded_current)
        levels.append(storage_to_level(current, h))
        area_m2 = storage_to_area(current, h)
        areas.append(area_m2)
        physical_violations.append(bool(violation_type))
        physical_violation_types.append(violation_type)
        physical_limit_excesses.append(excess)
        prev_dt = dt

    result = pd.DataFrame({
        "datetime": pd.to_datetime(sim["datetime"]),
        "reservoir_name_en": reservoir_name,
        "scenario_name": scenario_name,
        "inflow_m3s": pd.to_numeric(sim["inflow_m3s"], errors="coerce"),
        "outflow_m3s": pd.to_numeric(sim["outflow_m3s"], errors="coerce"),
        "storage_m3": storages,
        "storage_mcm": np.array(storages) / 1e6,
        "unbounded_storage_m3": unbounded_storages,
        "unbounded_storage_mcm": np.array(unbounded_storages) / 1e6,
        "water_level_m": levels,
        "area_m2": areas,
        "area_km2": np.array(areas) / 1e6,
        "physical_limit_violation": physical_violations,
        "physical_limit_type": physical_violation_types,
        "physical_limit_excess_m3": physical_limit_excesses,
        "physical_limit_excess_mcm": np.array(physical_limit_excesses) / 1e6,
        "outside_hypsometry_range": physical_violations,
    })
    return result
