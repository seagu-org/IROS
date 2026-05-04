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
    if "elevation_m" not in out.columns:
        raise ValueError("Missing hypsometry column: elevation_m")
    if "volume_m3" not in out.columns and "volume_mcm" not in out.columns:
        raise ValueError("Missing hypsometry column: volume_m3 or volume_mcm")
    out["elevation_m"] = pd.to_numeric(out["elevation_m"], errors="coerce")
    if "volume_m3" in out.columns:
        out["volume_m3"] = pd.to_numeric(out["volume_m3"], errors="coerce")
    else:
        out["volume_m3"] = pd.to_numeric(out["volume_mcm"], errors="coerce") * 1e6
    if "volume_mcm" in out.columns:
        out["volume_mcm"] = pd.to_numeric(out["volume_mcm"], errors="coerce")
    else:
        out["volume_mcm"] = out["volume_m3"] / 1e6
    if "area_m2" in out.columns:
        out["area_m2"] = pd.to_numeric(out["area_m2"], errors="coerce")
    elif "area_km2" in out.columns:
        out["area_m2"] = pd.to_numeric(out["area_km2"], errors="coerce") * 1e6
    else:
        out["area_m2"] = np.nan
    if "area_km2" in out.columns:
        out["area_km2"] = pd.to_numeric(out["area_km2"], errors="coerce")
    else:
        out["area_km2"] = out["area_m2"] / 1e6
    out = out.dropna(subset=["elevation_m", "volume_mcm"])
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


def estimate_outflow_from_inflow_and_level(obs_df, hypsometry_df):
    """Estimate default outflow from inflow and observed reservoir level.

    The estimate uses mass balance:
    Qout = Qin - (storage_t - storage_t_minus_1) / dt_seconds.
    It is an estimated default series, not an observed outflow series.
    """
    output_columns = [
        "datetime",
        "storage_m3",
        "storage_mcm",
        "storage_change_m3",
        "dt_seconds",
        "estimated_outflow_m3s",
        "negative_outflow_flag",
        "outside_reasonable_range_flag",
        "missing_water_level_flag",
        "missing_inflow_flag",
    ]
    if obs_df is None or obs_df.empty:
        return pd.DataFrame(columns=output_columns)

    out = obs_df.copy()
    if "datetime" not in out.columns:
        raise ValueError("Observed timeseries must include datetime")
    if "water_level_m" not in out.columns:
        out["water_level_m"] = np.nan
    if "inflow_m3s" not in out.columns:
        out["inflow_m3s"] = np.nan

    out["datetime"] = pd.to_datetime(out["datetime"], errors="coerce")
    out["water_level_m"] = pd.to_numeric(out["water_level_m"], errors="coerce")
    out["inflow_m3s"] = pd.to_numeric(out["inflow_m3s"], errors="coerce")
    out = out.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)

    h = prepare_hypsometry(hypsometry_df)
    min_level = h["elevation_m"].min() if not h.empty else np.nan
    max_level = h["elevation_m"].max() if not h.empty else np.nan
    water = out["water_level_m"]
    out["missing_water_level_flag"] = water.isna()
    out["missing_inflow_flag"] = out["inflow_m3s"].isna()
    outside_aev_level = water.notna() & (
        pd.isna(min_level) | pd.isna(max_level) | (water < min_level) | (water > max_level)
    )

    out["storage_m3"] = water.map(lambda level: level_to_storage(level, h))
    out["storage_mcm"] = out["storage_m3"] / 1e6
    out["storage_change_m3"] = out["storage_m3"] - out["storage_m3"].shift(1)
    out["dt_seconds"] = out["datetime"].diff().dt.total_seconds()
    valid_dt = out["dt_seconds"] > 0
    out["estimated_outflow_m3s"] = np.nan
    valid_estimate = (
        valid_dt
        & out["storage_change_m3"].notna()
        & out["inflow_m3s"].notna()
        & out["storage_m3"].notna()
    )
    out.loc[valid_estimate, "estimated_outflow_m3s"] = (
        out.loc[valid_estimate, "inflow_m3s"]
        - out.loc[valid_estimate, "storage_change_m3"] / out.loc[valid_estimate, "dt_seconds"]
    )
    out["negative_outflow_flag"] = out["estimated_outflow_m3s"] < 0
    invalid_dt_after_first = out.index.to_series().gt(0) & ~valid_dt.fillna(False)
    out["outside_reasonable_range_flag"] = outside_aev_level | invalid_dt_after_first
    return out


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
    outflow_source = scenario_outflow_df.get("outflow_source", pd.Series(["observed_outflow_m3s"])).iloc[0]
    if "outflow_m3s" not in sim.columns:
        sim["outflow_m3s"] = sim["outflow_m3s_default"]
    elif outflow_source != "Qout_estimated_default":
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
