from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots


SCENARIO_COLORS = [
    "#1f77b4",
    "#d62728",
    "#2ca02c",
    "#9467bd",
    "#ff7f0e",
    "#17becf",
    "#8c564b",
    "#e377c2",
]


STATIC_VN_LABELS = {
    "constant": "không đổi",
    "default": "mặc định",
    "manual": "thủ công",
    "window": "khoảng thời gian",
}


def _load_terms():
    terms_path = Path(__file__).resolve().parents[2] / "data" / "terms_vn.csv"
    if not terms_path.exists():
        return {}
    terms = {}
    with terms_path.open("r", encoding="utf-8-sig") as handle:
        next(handle, None)
        for line in handle:
            en, _, vn = line.strip().partition(",")
            if en and vn:
                terms[en] = vn
    return terms


def _vn_label(value):
    text = str(value)
    if text.startswith("V_"):
        return "Dung tích " + _vn_label(text[2:]).lower()
    if text.startswith("multiplier_"):
        return "hệ số " + text.removeprefix("multiplier_").replace("_", ".")
    return _load_terms().get(text, STATIC_VN_LABELS.get(text, text))


def _scenario_suffix(name):
    aliases = {
        "constant_outflow": "constant",
        "time_window_adjustment": "window",
        "manual_outflow": "manual",
    }
    if name == "default_outflow":
        return "default"
    if name in aliases:
        return aliases[name]
    if name.endswith("_outflow"):
        return name[: -len("_outflow")]
    return name


def _display_label(value):
    return _vn_label(value)


def _scenario_color_map(scenario_names):
    color_map = {}
    next_color_idx = 1
    for name in scenario_names:
        if name == "default_outflow":
            color_map[name] = SCENARIO_COLORS[0]
        else:
            color_map[name] = SCENARIO_COLORS[next_color_idx % len(SCENARIO_COLORS)]
            next_color_idx += 1
    return color_map


def plot_reservoir_timeseries(obs_df, scenario_results, level_reference_df=None):
    scenario_colors = _scenario_color_map(scenario_results.keys())
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=("Lưu lượng", "Mực nước", "Dung tích"),
    )
    fig.add_trace(
        go.Scatter(
            x=obs_df["datetime"],
            y=obs_df["inflow_m3s"],
            name="Qin",
            mode="lines",
            line={"color": "#4d4d4d"},
            hovertemplate="Ngày giờ=%{x|%Y-%m-%d %H:%M}<br>Giá trị=%{y:.2f} m3/s<extra></extra>",
        ),
        row=1,
        col=1,
    )
    default_payload = scenario_results.get("default_outflow")
    default_source = default_payload.get("outflow_source") if isinstance(default_payload, dict) else None
    if default_source == "Qout_estimated_default" and isinstance(default_payload, dict):
        default_df = default_payload["simulation"]
        default_name = "Qout ước tính mặc định"
    else:
        default_df = obs_df
        default_name = "Qout mặc định"
    if default_df is not None and "outflow_m3s" in default_df:
        fig.add_trace(
            go.Scatter(
                x=default_df["datetime"],
                y=default_df["outflow_m3s"],
                name=default_name,
                mode="lines",
                line={"color": SCENARIO_COLORS[0]},
                hovertemplate="Ngày giờ=%{x|%Y-%m-%d %H:%M}<br>Giá trị=%{y:.2f} m3/s<extra></extra>",
            ),
            row=1,
            col=1,
        )

    for name, payload in scenario_results.items():
        sim = payload["simulation"] if isinstance(payload, dict) else payload
        suffix = _scenario_suffix(name)
        color = scenario_colors[name]
        if name != "default_outflow":
            fig.add_trace(
                go.Scatter(
                    x=sim["datetime"],
                    y=sim["outflow_m3s"],
                    name=f"Qout {_display_label(suffix)}",
                    mode="lines",
                    line={"color": color},
                    hovertemplate="Ngày giờ=%{x|%Y-%m-%d %H:%M}<br>Giá trị=%{y:.2f} m3/s<extra></extra>",
                ),
                row=1,
                col=1,
            )
        fig.add_trace(
            go.Scatter(
                x=sim["datetime"],
                y=sim["water_level_m"],
                name=f"Mực nước {_display_label(suffix)}",
                mode="lines",
                line={"color": color},
                hovertemplate="Ngày giờ=%{x|%Y-%m-%d %H:%M}<br>Giá trị=%{y:.2f} m<extra></extra>",
            ),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=sim["datetime"],
                y=sim["storage_mcm"],
                name=f"Dung tích {_display_label(suffix)}",
                mode="lines",
                line={"color": color},
                hovertemplate="Ngày giờ=%{x|%Y-%m-%d %H:%M}<br>Giá trị=%{y:.2f} triệu m3<extra></extra>",
            ),
            row=3,
            col=1,
        )

    if level_reference_df is not None and not level_reference_df.empty:
        level_rows = level_reference_df.dropna(subset=["level_m"]) if "level_m" in level_reference_df else level_reference_df.iloc[0:0]
        for label, group in level_rows.groupby("level_label"):
            fig.add_trace(
                go.Scatter(
                    x=group["datetime"],
                    y=group["level_m"],
                    name=_display_label(label),
                    mode="lines",
                    line={"dash": "dash"},
                    hoverinfo="skip",
                ),
                row=2,
                col=1,
            )
        storage_rows = level_reference_df.dropna(subset=["storage_mcm"]) if "storage_mcm" in level_reference_df else level_reference_df.iloc[0:0]
        for label, group in storage_rows.groupby("storage_label"):
            fig.add_trace(
                go.Scatter(
                    x=group["datetime"],
                    y=group["storage_mcm"],
                    name=_display_label(label),
                    mode="lines",
                    line={"dash": "dash"},
                    hoverinfo="skip",
                ),
                row=3,
                col=1,
            )

    fig.update_yaxes(title_text="Lưu lượng (m3/s)", row=1, col=1)
    fig.update_yaxes(title_text="Mực nước (m)", row=2, col=1)
    fig.update_yaxes(title_text="Dung tích (triệu m3)", row=3, col=1)
    fig.update_layout(height=880, hovermode="closest", legend_title_text="Chuỗi")
    return fig
