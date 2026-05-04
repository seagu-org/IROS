from __future__ import annotations

import sys
import html
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reservoir_dashboard.src.constraints import (
    get_active_constraints_for_window_end,
    get_window_end_datetime,
)
from reservoir_dashboard.src.data_loading import (
    filter_time_window,
    get_initial_water_level,
    load_clean_observed_timeseries,
    load_hypsometry,
    load_level_constraints,
    load_reservoir_ids,
    load_reservoir_parameters,
    load_uploaded_observed_timeseries,
)
from reservoir_dashboard.src.excel_conversion import convert_all_q_excel_to_csv, find_excel_for_reservoir
from reservoir_dashboard.src.metrics import calculate_end_of_window_capacity_metrics, derive_reservoir_capacity_targets
from reservoir_dashboard.src.plotting import plot_reservoir_timeseries
from reservoir_dashboard.src.reservoir_model import (
    estimate_outflow_from_inflow_and_level,
    level_to_storage,
    simulate_reservoir,
    summarize_physical_limit_violations,
)
from reservoir_dashboard.src.scenarios import (
    compare_scenarios,
    default_outflow_values,
    make_constant_outflow,
    make_default_outflow,
    make_manual_outflow,
    make_multiplier_outflow,
    make_time_window_outflow,
)
from reservoir_dashboard.src.utils import as_csv_bytes, normalize_key


DATA = ROOT / "data"
Q_FOLDER = DATA / "Q" / "2025"
CSV_FOLDER = DATA / "Q" / "csv"


WINDOW_OPTIONS = {
    "24 giờ": "24 hours",
    "48 giờ": "48 hours",
    "72 giờ": "72 hours",
    "1 tuần": "1 week",
    "2 tuần": "2 weeks",
    "Tùy chỉnh": "custom",
}

SCENARIO_TYPE_OPTIONS = {
    "Dùng lưu lượng xả mặc định": "Use default outflow",
    "Lưu lượng xả không đổi": "Constant outflow",
    "Kịch bản hệ số nhân": "Multiplier scenario",
    "Điều chỉnh theo khoảng thời gian": "Time-window adjustment",
    "Chỉnh sửa bảng thủ công": "Manual table editor",
}

STATIC_VN_LABELS = {
    "active_season": "Mùa đang áp dụng",
    "ambiguous_or_missing": "Không rõ hoặc thiếu",
    "area_km2": "Diện tích (km2)",
    "capacity_target_m3": "Dung tích mục tiêu (m3)",
    "capacity_target_type": "Loại dung tích mục tiêu",
    "capacity_used_percentage": "Tỷ lệ dung tích đã sử dụng (%)",
    "capacity_used_pct": "Tỷ lệ dung tích đã sử dụng (%)",
    "cleaned_csv_path": "Đường dẫn CSV đã làm sạch",
    "constant_outflow": "Lưu lượng xả không đổi",
    "constraint_type": "Loại ràng buộc",
    "CSV water_level_m": "Mực nước trong CSV",
    "custom_initial_water_level_m": "Mực nước ban đầu tùy chỉnh (m)",
    "date": "Ngày",
    "datetime": "Ngày giờ",
    "dead_storage": "Dung tích chết",
    "default_outflow": "Lưu lượng xả mặc định",
    "default_outflow_source": "Nguồn lưu lượng xả mặc định",
    "design_flood_level_capacity_m3": "Dung tích tại mực nước lũ thiết kế (m3)",
    "days_to_fill_from_average_inflow": "Số ngày để đầy theo lưu lượng đến trung bình",
    "days_to_fill_from_inflow_only": "Số ngày để đầy theo lưu lượng đến",
    "dry_season": "Mùa cạn",
    "elevation_m": "Cao trình (m)",
    "estimated_outflow_m3s": "Lưu lượng xả ước tính (m3/s)",
    "final_capacity_used_pct": "Tỷ lệ dung tích cuối kỳ đã sử dụng (%)",
    "final_simulated_water_level_m": "Mực nước mô phỏng cuối kỳ (m)",
    "final_storage_m3": "Dung tích cuối kỳ (m3)",
    "final_storage_mcm": "Dung tích cuối kỳ (triệu m3)",
    "final_water_level_m": "Mực nước cuối kỳ (m)",
    "flood_check_level_capacity_m3": "Dung tích tại mực nước lũ kiểm tra (m3)",
    "flood_season": "Mùa lũ",
    "hour": "Giờ",
    "hours_to_fill_from_average_inflow": "Số giờ để đầy theo lưu lượng đến trung bình",
    "hours_to_fill_from_inflow_only": "Số giờ để đầy theo lưu lượng đến",
    "hypsometry_source": "Nguồn đường quan hệ AEV",
    "id": "Mã",
    "ids": "Danh sách mã",
    "inflow_m3s": "Lưu lượng đến (m3/s)",
    "inflow_range_m3s": "Khoảng lưu lượng đến (m3/s)",
    "initial_storage_mcm": "Dung tích ban đầu (triệu m3)",
    "initial_water_level_m": "Mực nước ban đầu (m)",
    "initial_water_level_source": "Nguồn mực nước ban đầu",
    "level_label": "Tên mực nước",
    "level_max_m": "Mực nước lớn nhất (m)",
    "level_m": "Mực nước (m)",
    "level_min_m": "Mực nước nhỏ nhất (m)",
    "manual_outflow": "Lưu lượng xả thủ công",
    "missing_inflow_flag": "Thiếu lưu lượng đến",
    "missing_water_level_flag": "Thiếu mực nước hồ",
    "max_capacity_used_pct": "Tỷ lệ dung tích lớn nhất đã sử dụng (%)",
    "max_physical_limit_excess_mcm": "Dung tích bị cắt lớn nhất (triệu m3)",
    "max_simulated_water_level_m": "Mực nước mô phỏng lớn nhất (m)",
    "max_storage_m3": "Dung tích lớn nhất (m3)",
    "max_water_level_m": "Mực nước lớn nhất (m)",
    "maximum_aev_volume_m3": "Dung tích AEV lớn nhất (m3)",
    "maximum_capacity_m3": "Dung tích lớn nhất (m3)",
    "min_simulated_water_level_m": "Mực nước mô phỏng nhỏ nhất (m)",
    "min_water_level_m": "Mực nước nhỏ nhất (m)",
    "negative_outflow_flag": "Lưu lượng xả ước tính âm",
    "normal_water_level_capacity_m3": "Dung tích tại mực nước dâng bình thường (m3)",
    "observed_outflow_m3s": "Lưu lượng xả trong CSV",
    "outflow_m3s": "Lưu lượng xả (m3/s)",
    "outflow_range_m3s": "Khoảng lưu lượng xả (m3/s)",
    "outside_reasonable_range_flag": "Ngoài khoảng hợp lý",
    "parameter_name": "Tên thông số",
    "period_end_mmdd": "Ngày kết thúc kỳ (mmdd)",
    "period_start_mmdd": "Ngày bắt đầu kỳ (mmdd)",
    "physical_limit": "Giới hạn vật lý",
    "lower_physical_limit": "Giới hạn vật lý dưới",
    "upper_physical_limit": "Giới hạn vật lý trên",
    "physical_limit_excess_mcm": "Dung tích bị cắt (triệu m3)",
    "physical_limit_first_datetime": "Thời điểm đầu tiên chạm giới hạn vật lý",
    "physical_limit_last_datetime": "Thời điểm cuối cùng chạm giới hạn vật lý",
    "physical_limit_type": "Loại giới hạn vật lý",
    "physical_limit_types": "Các loại giới hạn vật lý",
    "physical_limit_violation": "Chạm giới hạn vật lý",
    "physical_limit_violation_count": "Số bước thời gian chạm giới hạn vật lý",
    "possible_simulation_period": "Thời kỳ mô phỏng khả dụng",
    "Qout_estimated_default": "Qout ước tính mặc định",
    "regulation_id": "Mã quy định",
    "remaining_percentage": "Tỷ lệ dung tích còn lại (%)",
    "remaining_pct": "Tỷ lệ dung tích còn lại (%)",
    "remaining_storage_m3": "Dung tích còn lại (m3)",
    "remaining_storage_mcm": "Dung tích còn lại (triệu m3)",
    "reservoir_name_en": "Tên hồ chứa",
    "scenario_name": "Tên kịch bản",
    "season": "Mùa",
    "selected_simulation_end_datetime": "Thời điểm kết thúc mô phỏng đã chọn",
    "selected_simulation_start_datetime": "Thời điểm bắt đầu mô phỏng đã chọn",
    "storage_label": "Tên dung tích",
    "storage_m3": "Dung tích (m3)",
    "storage_mcm": "Dung tích (triệu m3)",
    "time_window_adjustment": "Điều chỉnh theo khoảng thời gian",
    "total_storage_at_nwl_m3": "Tổng dung tích tại mực nước dâng bình thường (m3)",
    "unavailable": "Không có dữ liệu",
    "unbounded_storage_m3": "Dung tích chưa giới hạn (m3)",
    "unit": "Đơn vị",
    "value": "Giá trị",
    "volume_m3": "Dung tích (m3)",
    "water_level_m": "Mực nước (m)",
}


@st.cache_data(show_spinner=False)
def load_vietnamese_terms():
    terms_path = DATA / "terms_vn.csv"
    if not terms_path.exists():
        return {}
    terms_df = pd.read_csv(terms_path)
    if {"EN_terms", "VN_terms"}.issubset(terms_df.columns):
        return dict(zip(terms_df["EN_terms"].astype(str), terms_df["VN_terms"].astype(str)))
    return {}


st.set_page_config(page_title="Bảng điều khiển vận hành hồ thủy điện", layout="wide")
st.title("Bảng điều khiển vận hành hồ thủy điện")


@st.cache_data(show_spinner=False)
def cached_load_inputs():
    return (
        load_reservoir_ids(DATA / "reservoir_id.csv"),
        load_reservoir_parameters(DATA / "reservoir_parameters.csv"),
        load_level_constraints(DATA / "level_constraints.csv"),
    )


def parameters_for_reservoir(parameters_df, reservoir_name):
    if parameters_df is None or parameters_df.empty or "reservoir_name_en" not in parameters_df:
        return pd.DataFrame()
    return parameters_df[parameters_df["reservoir_name_en"].astype(str).map(normalize_key) == normalize_key(reservoir_name)].copy()


def active_season_from_rows(active_rows, selected_mode):
    if selected_mode == "Flood season":
        return "flood_season", ["flood_season"]
    if selected_mode == "Dry season":
        return "dry_season", ["dry_season"]
    if active_rows is None or active_rows.empty:
        return None, []
    seasons = sorted([s for s in active_rows.get("season", pd.Series(dtype=str)).dropna().astype(str).unique()])
    if len(seasons) == 1:
        return seasons[0], seasons
    return None, seasons


def get_parameter_value(parameter_rows, parameter_name):
    if parameter_rows is None or parameter_rows.empty or "parameter_name" not in parameter_rows:
        return np.nan
    rows = parameter_rows[parameter_rows["parameter_name"].astype(str).str.lower() == parameter_name]
    if rows.empty:
        return np.nan
    return pd.to_numeric(rows.iloc[0].get("value"), errors="coerce")


def get_parameter_unit(parameter_rows, parameter_name):
    if parameter_rows is None or parameter_rows.empty or "parameter_name" not in parameter_rows:
        return None
    rows = parameter_rows[parameter_rows["parameter_name"].astype(str).str.lower() == parameter_name]
    if rows.empty:
        return None
    return rows.iloc[0].get("unit")


def storage_parameter_to_mcm(value, unit):
    if pd.isna(value):
        return np.nan
    unit_text = str(unit or "").lower()
    value = float(value)
    if "10^6" in unit_text or "million" in unit_text or "mcm" in unit_text:
        return value
    if abs(value) > 10000:
        return value / 1e6
    return value


def build_parameter_level_reference_series(sim_df, parameter_rows, active_season, hypsometry_df=None):
    columns = ["datetime", "level_label", "level_m", "storage_label", "storage_mcm"]
    if sim_df is None or sim_df.empty:
        return pd.DataFrame(columns=columns)
    if active_season == "flood_season":
        names = [
            "normal_water_level",
            "dead_water_level",
            "design_flood_level",
            "flood_check_level",
        ]
    else:
        names = ["normal_water_level", "dead_water_level"]
    datetimes = pd.to_datetime(sim_df["datetime"], errors="coerce").dropna().sort_values().unique()
    rows = []
    for name in names:
        level = get_parameter_value(parameter_rows, name)
        if pd.isna(level):
            continue
        storage_mcm = np.nan
        if hypsometry_df is not None and not hypsometry_df.empty:
            storage_m3 = level_to_storage(level, hypsometry_df)
            storage_mcm = storage_m3 / 1e6 if pd.notna(storage_m3) else np.nan
        for dt in datetimes:
            rows.append({
                "datetime": dt,
                "level_label": name,
                "level_m": float(level),
                "storage_label": f"V_{name}",
                "storage_mcm": storage_mcm,
            })
    existing_storage_labels = {row["storage_label"] for row in rows if pd.notna(row.get("storage_mcm"))}
    direct_storage_names = []
    if "V_normal_water_level" not in existing_storage_labels:
        direct_storage_names.append(("total_storage_at_nwl", "V_total_storage_at_nwl"))
    if "V_dead_water_level" not in existing_storage_labels:
        direct_storage_names.append(("dead_storage", "V_dead_storage"))
    for parameter_name, label in direct_storage_names:
        if label in existing_storage_labels:
            continue
        storage_value = get_parameter_value(parameter_rows, parameter_name)
        storage_unit = get_parameter_unit(parameter_rows, parameter_name)
        storage_mcm = storage_parameter_to_mcm(storage_value, storage_unit)
        if pd.isna(storage_mcm):
            continue
        for dt in datetimes:
            rows.append({
                "datetime": dt,
                "level_label": np.nan,
                "level_m": np.nan,
                "storage_label": label,
                "storage_mcm": storage_mcm,
            })
    return pd.DataFrame(rows, columns=columns)


def display_path_from_working_directory(path_value):
    if not path_value:
        return ""
    path = Path(path_value)
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def display_label(value):
    text = str(value)
    if text.startswith("V_"):
        return "Dung tích " + display_label(text[2:]).lower()
    if text.startswith("multiplier_"):
        return "Hệ số nhân " + text.removeprefix("multiplier_").replace("_", ".")
    terms = load_vietnamese_terms()
    return terms.get(text, STATIC_VN_LABELS.get(text, text))


def display_value(value):
    if not isinstance(value, str):
        return value
    if "\\" in value or "/" in value or "." in value:
        return value
    if "," in value:
        return ", ".join(display_value(part.strip()) for part in value.split(","))
    return display_label(value)


def display_dataframe(df):
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in out.select_dtypes(include=["object"]).columns:
        out[col] = out[col].map(display_value)
    return out.rename(columns={col: display_label(col) for col in out.columns})


def datetime_range_label(df):
    if df is None or df.empty or "datetime" not in df:
        return "Không có dữ liệu"
    datetimes = pd.to_datetime(df["datetime"], errors="coerce").dropna()
    if datetimes.empty:
        return "Không có dữ liệu"
    return f"{datetimes.min()} đến {datetimes.max()}"


def format_summary_value(value):
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        dt = pd.to_datetime(value, errors="coerce")
        return "Không có dữ liệu" if pd.isna(dt) else dt.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, str):
        return str(display_value(value))
    if value is None:
        return "Không có dữ liệu"
    try:
        if pd.isna(value):
            return "Không có dữ liệu"
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float, np.integer, np.floating)):
        return f"{float(value):,.2f}"
    return str(display_value(value))


def display_summary_sections(sections):
    st.markdown(
        """
        <style>
        .summary-table {
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
            font-size: 0.92rem;
        }
        .summary-table th,
        .summary-table td {
            border: 1px solid #e6e8eb;
            padding: 0.55rem 0.65rem;
            text-align: left;
            vertical-align: top;
            white-space: normal;
            overflow-wrap: anywhere;
        }
        .summary-table th {
            background: #f7f8fa;
            color: #6b7280;
            font-weight: 500;
        }
        .summary-table td:first-child,
        .summary-table th:first-child {
            width: 58%;
        }
        .summary-table td:last-child,
        .summary-table th:last-child {
            width: 42%;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns(len(sections))
    for col, (title, rows) in zip(cols, sections):
        body_rows = "\n".join(
            "<tr>"
            f"<td>{html.escape(display_label(key))}</td>"
            f"<td>{html.escape(format_summary_value(value))}</td>"
            "</tr>"
            for key, value in rows
        )
        table_html = (
            '<table class="summary-table">'
            "<thead><tr><th>Chỉ tiêu</th><th>Giá trị</th></tr></thead>"
            f"<tbody>{body_rows}</tbody>"
            "</table>"
        )
        with col:
            st.markdown(f"**{title}**")
            st.markdown(table_html, unsafe_allow_html=True)


def warn_physical_limit_violations(sim_df, label):
    summary = summarize_physical_limit_violations(sim_df)
    if not summary:
        return
    count = summary.get("physical_limit_violation_count", 0)
    first_dt = summary.get("physical_limit_first_datetime")
    last_dt = summary.get("physical_limit_last_datetime")
    types = display_value(summary.get("physical_limit_types", "physical_limit"))
    excess = summary.get("max_physical_limit_excess_mcm", np.nan)
    excess_text = "Không có dữ liệu" if pd.isna(excess) else f"{excess:,.2f} triệu m3"
    st.warning(
        f"{label}: hồ chứa chạm giới hạn vật lý trong {count} bước thời gian "
        f"từ {first_dt} đến {last_dt}. Dung tích và mực nước được giữ tại "
        f"biên AEV. Loại: {types}. Dung tích bị cắt lớn nhất: {excess_text}."
    )


def has_usable_series(df, column):
    return df is not None and column in df.columns and pd.to_numeric(df[column], errors="coerce").notna().any()


def numeric_mean_or_zero(values):
    mean_value = pd.to_numeric(values, errors="coerce").mean()
    return float(mean_value) if pd.notna(mean_value) else 0.0


def prepare_default_outflow_inputs(selected_obs, hypsometry_df, source_choice="auto"):
    if selected_obs is None or selected_obs.empty:
        return selected_obs, "auto", None
    out = selected_obs.copy()
    if "outflow_m3s" not in out.columns:
        out["outflow_m3s"] = np.nan
    can_estimate = (
        not hypsometry_df.empty
        and has_usable_series(out, "inflow_m3s")
        and has_usable_series(out, "water_level_m")
    )
    if can_estimate:
        out = estimate_outflow_from_inflow_and_level(out, hypsometry_df)
    has_observed_outflow = has_usable_series(out, "outflow_m3s")
    if source_choice == "estimated" and can_estimate:
        return out, "estimated", "Qout_estimated_default"
    if not has_observed_outflow and can_estimate:
        return out, "estimated", "Qout_estimated_default"
    return out, "observed", "observed_outflow_m3s"


def warn_estimated_default_outflow(selected_obs):
    if selected_obs is None or selected_obs.empty or "estimated_outflow_m3s" not in selected_obs.columns:
        return
    st.info("Lưu lượng xả mặc định được ước tính từ lưu lượng đến và mực nước hồ bằng cân bằng khối lượng.")
    negative_count = int(selected_obs.get("negative_outflow_flag", pd.Series(dtype=bool)).fillna(False).sum())
    if negative_count:
        st.warning(
            "Lưu lượng xả ước tính có giá trị âm. Dashboard giữ nguyên giá trị này, không cắt về 0. "
            "Nguyên nhân có thể là lưu lượng đến bị đánh giá thấp, mực nước nhiễu, sai đường AEV, "
            "thiếu mưa trực tiếp trên mặt hồ, lệch timestamp, hoặc lỗi chất lượng dữ liệu."
        )
    flag_cols = [
        "negative_outflow_flag",
        "outside_reasonable_range_flag",
        "missing_water_level_flag",
        "missing_inflow_flag",
    ]
    counts = {
        col: int(selected_obs[col].fillna(False).sum())
        for col in flag_cols
        if col in selected_obs.columns and selected_obs[col].fillna(False).any()
    }
    if counts:
        shown_counts = {display_label(col): count for col, count in counts.items()}
        st.write("Cờ dữ liệu của lưu lượng xả ước tính:", shown_counts)


try:
    reservoir_ids, reservoir_parameters, level_constraints = cached_load_inputs()
except Exception as exc:
    st.error(f"Không thể tải các tệp đầu vào bắt buộc: {exc}")
    st.stop()

missing_excel = [
    name for name in reservoir_ids["reservoir_name_en"].dropna().astype(str)
    if find_excel_for_reservoir(Q_FOLDER, name) is None
]

with st.sidebar:
    reservoir_name = st.selectbox("Hồ chứa", reservoir_ids["reservoir_name_en"].dropna().astype(str).tolist())
    uploaded_timeseries_csv = st.file_uploader("Tải lên CSV lưu lượng đến/xả cho lần chạy này", type="csv")
    selected_mode = "Auto"

obs_df, csv_path = load_clean_observed_timeseries(CSV_FOLDER, reservoir_name)
if obs_df.empty:
    excel_path = find_excel_for_reservoir(Q_FOLDER, reservoir_name)
    if excel_path is not None:
        try:
            convert_all_q_excel_to_csv(Q_FOLDER, CSV_FOLDER, reservoir_ids)
            obs_df, csv_path = load_clean_observed_timeseries(CSV_FOLDER, reservoir_name)
        except Exception as exc:
            st.warning(f"Không thể tự động tạo CSV đã làm sạch từ Excel: {exc}")

if uploaded_timeseries_csv is not None:
    try:
        obs_df = load_uploaded_observed_timeseries(uploaded_timeseries_csv, reservoir_name)
        csv_path = uploaded_timeseries_csv.name
    except Exception as exc:
        st.error(f"Không thể đọc CSV lưu lượng đến/xả đã tải lên: {exc}")
        obs_df = pd.DataFrame()
        csv_path = uploaded_timeseries_csv.name

hypsometry_df, hypsometry_source = load_hypsometry(DATA / "AEV_obs", reservoir_name)
parameter_rows = parameters_for_reservoir(reservoir_parameters, reservoir_name)

with st.sidebar:
    if not obs_df.empty:
        min_dt = pd.to_datetime(obs_df["datetime"]).min()
        max_dt = pd.to_datetime(obs_df["datetime"]).max()
        start_date = st.date_input("Ngày bắt đầu", value=min_dt.date(), min_value=min_dt.date(), max_value=max_dt.date())
        start_hour = st.number_input("Giờ bắt đầu", min_value=0, max_value=23, value=int(min_dt.hour), step=1)
        start_datetime = pd.Timestamp(start_date) + pd.Timedelta(hours=int(start_hour))
        window_label = st.selectbox("Độ dài cửa sổ", list(WINDOW_OPTIONS.keys()))
        window_option = WINDOW_OPTIONS[window_label]
        custom_end_datetime = None
        if window_option == "custom":
            end_date = st.date_input("Ngày kết thúc tùy chỉnh", value=min(max_dt, start_datetime + pd.Timedelta(days=1)).date())
            end_hour = st.number_input("Giờ kết thúc tùy chỉnh", min_value=0, max_value=23, value=int(min(max_dt, start_datetime + pd.Timedelta(days=1)).hour), step=1)
            custom_end_datetime = pd.Timestamp(end_date) + pd.Timedelta(hours=int(end_hour))
    else:
        start_datetime = pd.NaT
        window_option = "24 hours"
        custom_end_datetime = None

selected_obs = filter_time_window(obs_df, start_datetime, window_option, custom_end_datetime) if not obs_df.empty else pd.DataFrame()
default_outflow_source_choice = "auto"
if not selected_obs.empty:
    has_observed_outflow = has_usable_series(selected_obs, "outflow_m3s")
    has_water_level = has_usable_series(selected_obs, "water_level_m")
    has_inflow = has_usable_series(selected_obs, "inflow_m3s")
    if has_observed_outflow and has_water_level and has_inflow and not hypsometry_df.empty:
        with st.sidebar:
            default_source_label = st.radio(
                "Nguồn lưu lượng xả mặc định",
                ["Dùng outflow_m3s trong CSV", "Ước tính Qout từ Qin và mực nước hồ"],
                index=0,
            )
        if default_source_label == "Ước tính Qout từ Qin và mực nước hồ":
            default_outflow_source_choice = "estimated"
selected_obs, default_outflow_source, default_outflow_label = prepare_default_outflow_inputs(
    selected_obs,
    hypsometry_df,
    default_outflow_source_choice,
)
initial_water_level_m, initial_datetime, exact_initial_level = get_initial_water_level(selected_obs)
initial_water_level_source = "CSV water_level_m"

with st.sidebar:
    if not selected_obs.empty and not hypsometry_df.empty:
        min_level = float(hypsometry_df["elevation_m"].min())
        max_level = float(hypsometry_df["elevation_m"].max())
        default_initial = initial_water_level_m if pd.notna(initial_water_level_m) else min_level
        initial_level_mode = st.radio(
            "Mực nước ban đầu",
            ["Dùng mực nước trong CSV", "Nhập giá trị tùy chỉnh"],
            index=0 if pd.notna(initial_water_level_m) else 1,
        )
        if initial_level_mode == "Nhập giá trị tùy chỉnh":
            initial_water_level_m = st.number_input(
                "Mực nước ban đầu tùy chỉnh (m)",
                min_value=min_level,
                max_value=max_level,
                value=float(default_initial),
            )
            initial_datetime = selected_obs["datetime"].min()
            exact_initial_level = True
            initial_water_level_source = "custom_initial_water_level_m"
        elif pd.isna(initial_water_level_m):
            st.warning("Cửa sổ CSV đã chọn không có mực nước dùng được. Hãy nhập mực nước ban đầu tùy chỉnh.")

if selected_obs.empty:
    window_end = pd.NaT
else:
    window_end = get_window_end_datetime(selected_obs)

active_season_rows = get_active_constraints_for_window_end(level_constraints, reservoir_name, window_end, selected_mode)
active_season, active_seasons = active_season_from_rows(active_season_rows, selected_mode)

capacity_targets = {}
baseline_sim = pd.DataFrame()
baseline_metrics = {}
level_reference_df = pd.DataFrame()

if (
    not selected_obs.empty
    and not hypsometry_df.empty
    and pd.notna(initial_water_level_m)
    and not default_outflow_values(selected_obs, default_outflow_source)[0].isna().all()
):
    default_outflow = make_default_outflow(selected_obs, default_outflow_source)
    baseline_sim = simulate_reservoir(selected_obs, default_outflow, initial_water_level_m, hypsometry_df, parameter_rows)
    level_reference_df = build_parameter_level_reference_series(baseline_sim, parameter_rows, active_season, hypsometry_df)
    capacity_targets = derive_reservoir_capacity_targets(parameter_rows, hypsometry_df, pd.DataFrame(), active_season)
    baseline_metrics = calculate_end_of_window_capacity_metrics(baseline_sim, selected_obs, capacity_targets, active_season)

tab_setup, tab_baseline, tab_scenarios, tab_diag = st.tabs([
    "Thiết lập hồ chứa",
    "Giai đoạn 1: mô phỏng cơ sở",
    "Giai đoạn 2: kịch bản xả",
    "Chẩn đoán dữ liệu",
])

with tab_setup:
    st.subheader("Thiết lập hồ chứa")
    if missing_excel:
        st.warning("Các hồ chứa không có tệp Excel tương ứng: " + ", ".join(missing_excel))

    c1, c2, c3 = st.columns(3)
    c1.write(f"{display_label('possible_simulation_period')}: {datetime_range_label(obs_df)}")
    c2.write(f"{display_label('selected_simulation_start_datetime')}: {selected_obs['datetime'].min() if not selected_obs.empty else 'Không có dữ liệu'}")
    c3.write(f"{display_label('selected_simulation_end_datetime')}: {window_end if pd.notna(window_end) else 'Không có dữ liệu'}")
    st.write(f"{display_label('initial_water_level_m')}: {initial_water_level_m if pd.notna(initial_water_level_m) else 'Không có dữ liệu'}")
    st.write(f"{display_label('initial_water_level_source')}: {display_value(initial_water_level_source)}")
    st.info("Mùa được chọn theo thời điểm cuối cùng của cửa sổ mô phỏng đã chọn.")
    if not exact_initial_level and pd.notna(initial_water_level_m):
        st.warning("Mực nước ban đầu dùng giá trị hợp lệ gần nhất vì thời điểm lưu lượng đến đầu tiên không có mực nước chính xác.")
    if len(active_seasons) > 1:
        st.warning("Có nhiều mùa cùng áp dụng tại ngày kết thúc cửa sổ đã chọn. Vui lòng kiểm tra các giai đoạn mùa trong level_constraints.csv.")
    st.write("Mùa đang áp dụng: " + (", ".join(display_value(season) for season in active_seasons) if active_seasons else "Không có dữ liệu"))
    if level_reference_df.empty:
        st.info("Không có đường tham chiếu mực nước theo mùa cho hồ chứa đã chọn.")
    else:
        st.write("Đường tham chiếu từ reservoir_parameters.csv và AEV")
        st.dataframe(
            display_dataframe(level_reference_df[["level_label", "level_m", "storage_label", "storage_mcm"]].drop_duplicates()),
            use_container_width=True,
        )
    st.write("Thông số hồ chứa")
    st.dataframe(display_dataframe(parameter_rows), use_container_width=True)

with tab_baseline:
    st.subheader("Giai đoạn 1: mô phỏng cơ sở")
    if selected_obs.empty:
        st.error("Không có chuỗi thời gian quan trắc đã làm sạch cho hồ chứa và cửa sổ đã chọn.")
    elif hypsometry_df.empty:
        st.error("Không có đường quan hệ AEV cho hồ chứa đã chọn. Mô phỏng bị tắt.")
    elif pd.isna(initial_water_level_m):
        st.error("Thiếu mực nước ban đầu. Hãy nhập mực nước ban đầu tùy chỉnh trong thanh bên.")
    elif selected_obs["inflow_m3s"].isna().all() or default_outflow_values(selected_obs, default_outflow_source)[0].isna().all():
        st.error("Thiếu lưu lượng đến hoặc lưu lượng xả. Mô phỏng bị tắt.")
    else:
        default_outflow_series, _ = default_outflow_values(selected_obs, default_outflow_source)
        if default_outflow_label == "Qout_estimated_default":
            warn_estimated_default_outflow(selected_obs)
        inflow_range = f"{selected_obs['inflow_m3s'].min():,.2f} đến {selected_obs['inflow_m3s'].max():,.2f}"
        outflow_range = f"{default_outflow_series.min():,.2f} đến {default_outflow_series.max():,.2f}"
        display_summary_sections(
            [
                (
                    "Cửa sổ và dữ liệu",
                    [
                        ("active_season", active_season or "ambiguous_or_missing"),
                        ("selected_simulation_start_datetime", selected_obs["datetime"].min()),
                        ("selected_simulation_end_datetime", selected_obs["datetime"].max()),
                        ("default_outflow_source", default_outflow_label),
                        ("inflow_range_m3s", inflow_range),
                        ("outflow_range_m3s", outflow_range),
                    ],
                ),
                (
                    "Mực nước và dung tích",
                    [
                        ("initial_water_level_m", initial_water_level_m),
                        ("initial_storage_mcm", level_to_storage(initial_water_level_m, hypsometry_df) / 1e6),
                        ("max_simulated_water_level_m", baseline_sim["water_level_m"].max()),
                        ("min_simulated_water_level_m", baseline_sim["water_level_m"].min()),
                        ("final_simulated_water_level_m", baseline_sim["water_level_m"].iloc[-1]),
                        ("final_storage_mcm", baseline_sim["storage_mcm"].iloc[-1]),
                    ],
                ),
                (
                    "Dung tích còn lại",
                    [
                        ("capacity_target_type", baseline_metrics.get("capacity_target_type", "unavailable")),
                        ("capacity_used_percentage", baseline_metrics.get("capacity_used_pct", np.nan)),
                        ("remaining_storage_mcm", baseline_metrics.get("remaining_storage_mcm", np.nan)),
                        ("remaining_percentage", baseline_metrics.get("remaining_pct", np.nan)),
                        ("hours_to_fill_from_average_inflow", baseline_metrics.get("hours_to_fill_from_inflow_only", np.nan)),
                        ("days_to_fill_from_average_inflow", baseline_metrics.get("days_to_fill_from_inflow_only", np.nan)),
                    ],
                ),
            ]
        )
        warn_physical_limit_violations(baseline_sim, "Mô phỏng cơ sở")
        st.plotly_chart(
            plot_reservoir_timeseries(
                selected_obs,
                {"default_outflow": {"simulation": baseline_sim, "outflow_source": default_outflow_label}},
                level_reference_df,
            ),
            use_container_width=True,
            key="baseline_timeseries_plot",
        )
        st.download_button("Tải CSV mô phỏng", as_csv_bytes(baseline_sim), "baseline_simulation.csv", "text/csv")
        st.download_button("Tải CSV quan trắc đã làm sạch", as_csv_bytes(selected_obs), "cleaned_observed_window.csv", "text/csv")

with tab_scenarios:
    st.subheader("Giai đoạn 2: kịch bản xả")
    if selected_obs.empty or hypsometry_df.empty or pd.isna(initial_water_level_m):
        st.error("Hãy chọn hồ chứa, cửa sổ thời gian, đường quan hệ AEV và mực nước ban đầu hợp lệ trước khi mô phỏng kịch bản.")
    else:
        scenario_type_label = st.selectbox("Loại kịch bản tùy chỉnh", list(SCENARIO_TYPE_OPTIONS.keys()))
        scenario_type = SCENARIO_TYPE_OPTIONS[scenario_type_label]
        default_outflow_series, _ = default_outflow_values(selected_obs, default_outflow_source)
        custom_outflow = make_default_outflow(selected_obs, default_outflow_source)
        if scenario_type == "Constant outflow":
            value = st.number_input("Lưu lượng xả không đổi (m3/s)", min_value=0.0, value=numeric_mean_or_zero(default_outflow_series))
            custom_outflow = make_constant_outflow(selected_obs, value)
        elif scenario_type == "Multiplier scenario":
            multiplier = st.number_input("Hệ số nhân lưu lượng xả", min_value=0.0, value=1.0, step=0.1)
            custom_outflow = make_multiplier_outflow(selected_obs, multiplier, default_outflow_source)
        elif scenario_type == "Time-window adjustment":
            adj_start = st.selectbox("Thời điểm bắt đầu điều chỉnh", selected_obs["datetime"].astype(str).tolist(), index=0)
            adj_end = st.selectbox("Thời điểm kết thúc điều chỉnh", selected_obs["datetime"].astype(str).tolist(), index=len(selected_obs) - 1)
            value = st.number_input("Lưu lượng xả thay thế (m3/s)", min_value=0.0, value=numeric_mean_or_zero(default_outflow_series), key="replacement_outflow")
            custom_outflow = make_time_window_outflow(selected_obs, adj_start, adj_end, value, default_outflow_source)
        elif scenario_type == "Manual table editor":
            edit_base = make_default_outflow(selected_obs, default_outflow_source)
            editable_columns = {display_label(col): col for col in edit_base.columns}
            edited = st.data_editor(
                edit_base.rename(columns={raw: shown for shown, raw in editable_columns.items()}),
                use_container_width=True,
                num_rows="fixed",
            ).rename(columns=editable_columns)
            custom_outflow = make_manual_outflow(edited)

        custom_name = custom_outflow["scenario_name"].iloc[0]
        default_sim = baseline_sim if not baseline_sim.empty else simulate_reservoir(selected_obs, make_default_outflow(selected_obs, default_outflow_source), initial_water_level_m, hypsometry_df, parameter_rows)
        custom_sim = simulate_reservoir(selected_obs, custom_outflow, initial_water_level_m, hypsometry_df, parameter_rows)
        scenario_results = {
            "default_outflow": {"simulation": default_sim, "obs_df": selected_obs, "outflow_source": default_outflow_label},
            custom_name: {"simulation": custom_sim, "obs_df": selected_obs},
        }
        if custom_name == "default_outflow":
            scenario_results = {
                "default_outflow": {"simulation": default_sim, "obs_df": selected_obs, "outflow_source": default_outflow_label}
            }
        comparison = compare_scenarios(scenario_results, pd.DataFrame(), capacity_targets)
        warn_physical_limit_violations(default_sim, "Mô phỏng lưu lượng xả mặc định")
        warn_physical_limit_violations(custom_sim, f"Mô phỏng {display_value(custom_name)}")
        st.plotly_chart(
            plot_reservoir_timeseries(
                selected_obs,
                scenario_results,
                build_parameter_level_reference_series(custom_sim, parameter_rows, active_season, hypsometry_df),
            ),
            use_container_width=True,
            key=f"scenario_timeseries_plot_{custom_name}",
        )
        st.dataframe(display_dataframe(comparison), use_container_width=True)
        st.download_button("Tải CSV kịch bản xả đã chọn", as_csv_bytes(custom_outflow), "selected_outflow_scenario.csv", "text/csv")
        st.download_button("Tải CSV mô phỏng kịch bản", as_csv_bytes(custom_sim), "scenario_simulation.csv", "text/csv")

with tab_diag:
    st.subheader("Chẩn đoán dữ liệu")
    st.write({
        display_label("cleaned_csv_path"): display_path_from_working_directory(csv_path),
        display_label("hypsometry_source"): display_path_from_working_directory(hypsometry_source),
    })
    st.write("Danh sách hồ chứa")
    st.dataframe(display_dataframe(reservoir_ids), use_container_width=True)
    st.write("Mẫu CSV đã làm sạch")
    st.write(f"{display_label('possible_simulation_period')}: {datetime_range_label(obs_df)}")
    st.dataframe(display_dataframe(obs_df.head(20)), use_container_width=True)
    st.write("Mẫu đường quan hệ AEV")
    st.dataframe(display_dataframe(hypsometry_df.head(20)), use_container_width=True)
    st.write("Các dòng nguồn mùa cho hồ chứa đã chọn")
    season_source_rows = level_constraints[level_constraints["reservoir_name_en"].astype(str).map(normalize_key) == normalize_key(reservoir_name)]
    st.dataframe(display_dataframe(season_source_rows), use_container_width=True)
