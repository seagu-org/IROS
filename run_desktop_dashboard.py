from __future__ import annotations

import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QDate, QModelIndex, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QDoubleSpinBox,
    QSplitter,
    QTableView,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure

from reservoir_dashboard.src.constraints import (
    get_active_constraints_for_window_end,
    get_window_end_datetime,
)
from reservoir_dashboard.src.data_loading import (
    clean_observed_timeseries_dataframe,
    filter_time_window,
    get_initial_water_level,
    load_clean_observed_timeseries,
    load_hypsometry,
    load_level_constraints,
    load_reservoir_ids,
    load_reservoir_parameters,
)
from reservoir_dashboard.src.metrics import (
    calculate_end_of_window_capacity_metrics,
    derive_reservoir_capacity_targets,
)
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
    make_multiplier_outflow,
    make_time_window_outflow,
)
from reservoir_dashboard.src.utils import normalize_key


WINDOW_OPTIONS = {
    "24 giờ": "24 hours",
    "48 giờ": "48 hours",
    "72 giờ": "72 hours",
    "1 tuần": "1 week",
    "2 tuần": "2 weeks",
    "Tùy chỉnh": "custom",
}

SCENARIO_OPTIONS = {
    "Dùng lưu lượng xả mặc định": "default",
    "Lưu lượng xả không đổi": "constant",
    "Nhân lưu lượng xả theo hệ số": "multiplier",
    "Thay thế lưu lượng xả theo khoảng thời gian": "time_window",
}


def app_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


ROOT = app_root()
DATA = ROOT / "data"
CSV_FOLDER = DATA / "Q" / "csv"


def parameters_for_reservoir(parameters_df: pd.DataFrame, reservoir_name: str) -> pd.DataFrame:
    if parameters_df is None or parameters_df.empty or "reservoir_name_en" not in parameters_df:
        return pd.DataFrame()
    key = normalize_key(reservoir_name)
    return parameters_df[parameters_df["reservoir_name_en"].astype(str).map(normalize_key) == key].copy()


def active_season_from_rows(active_rows: pd.DataFrame) -> tuple[str | None, list[str]]:
    if active_rows is None or active_rows.empty:
        return None, []
    seasons = sorted(active_rows.get("season", pd.Series(dtype=str)).dropna().astype(str).unique())
    if len(seasons) == 1:
        return seasons[0], seasons
    return None, seasons


def get_parameter_value(parameter_rows: pd.DataFrame, parameter_name: str) -> float:
    if parameter_rows is None or parameter_rows.empty or "parameter_name" not in parameter_rows:
        return np.nan
    rows = parameter_rows[parameter_rows["parameter_name"].astype(str).str.lower() == parameter_name]
    if rows.empty:
        return np.nan
    return pd.to_numeric(rows.iloc[0].get("value"), errors="coerce")


def get_parameter_unit(parameter_rows: pd.DataFrame, parameter_name: str) -> str | None:
    if parameter_rows is None or parameter_rows.empty or "parameter_name" not in parameter_rows:
        return None
    rows = parameter_rows[parameter_rows["parameter_name"].astype(str).str.lower() == parameter_name]
    if rows.empty:
        return None
    return rows.iloc[0].get("unit")


def storage_parameter_to_mcm(value: float, unit: str | None) -> float:
    if pd.isna(value):
        return np.nan
    value = float(value)
    unit_text = str(unit or "").lower()
    if "10^6" in unit_text or "million" in unit_text or "mcm" in unit_text:
        return value
    if abs(value) > 10000:
        return value / 1e6
    return value


def build_parameter_level_reference_series(
    sim_df: pd.DataFrame,
    parameter_rows: pd.DataFrame,
    active_season: str | None,
    hypsometry_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    columns = ["datetime", "level_label", "level_m", "storage_label", "storage_mcm"]
    if sim_df is None or sim_df.empty:
        return pd.DataFrame(columns=columns)
    names = ["normal_water_level", "dead_water_level"]
    if active_season == "flood_season":
        names += ["design_flood_level", "flood_check_level"]
    datetimes = pd.to_datetime(sim_df["datetime"], errors="coerce").dropna().sort_values().unique()
    rows: list[dict[str, object]] = []
    for name in names:
        level = get_parameter_value(parameter_rows, name)
        if pd.isna(level):
            continue
        storage_mcm = np.nan
        if hypsometry_df is not None and not hypsometry_df.empty:
            storage_m3 = level_to_storage(level, hypsometry_df)
            storage_mcm = storage_m3 / 1e6 if pd.notna(storage_m3) else np.nan
        for dt in datetimes:
            rows.append(
                {
                    "datetime": dt,
                    "level_label": name,
                    "level_m": float(level),
                    "storage_label": f"V_{name}",
                    "storage_mcm": storage_mcm,
                }
            )
    existing = {row["storage_label"] for row in rows if pd.notna(row.get("storage_mcm"))}
    for parameter_name, label in [
        ("total_storage_at_nwl", "V_total_storage_at_nwl"),
        ("dead_storage", "V_dead_storage"),
    ]:
        if label in existing:
            continue
        storage_mcm = storage_parameter_to_mcm(
            get_parameter_value(parameter_rows, parameter_name),
            get_parameter_unit(parameter_rows, parameter_name),
        )
        if pd.isna(storage_mcm):
            continue
        for dt in datetimes:
            rows.append(
                {
                    "datetime": dt,
                    "level_label": np.nan,
                    "level_m": np.nan,
                    "storage_label": label,
                    "storage_mcm": storage_mcm,
                }
            )
    return pd.DataFrame(rows, columns=columns)


def format_value(value: object) -> str:
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, (float, np.floating)):
        return f"{value:,.2f}"
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return str(pd.to_datetime(value))
    return "" if value is None else str(value)


def has_usable_series(df: pd.DataFrame, column: str) -> bool:
    return df is not None and column in df.columns and pd.to_numeric(df[column], errors="coerce").notna().any()


def numeric_mean_or_zero(values: object) -> float:
    mean_value = pd.to_numeric(values, errors="coerce").mean()
    return float(mean_value) if pd.notna(mean_value) else 0.0


def prepare_default_outflow_inputs(
    selected_obs: pd.DataFrame,
    hypsometry_df: pd.DataFrame,
    source_choice: str = "auto",
) -> tuple[pd.DataFrame, str, str]:
    if selected_obs is None or selected_obs.empty:
        return selected_obs, "auto", ""
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


class DataFrameModel(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame | None = None) -> None:
        super().__init__()
        self._df = df if df is not None else pd.DataFrame()

    def set_dataframe(self, df: pd.DataFrame | None) -> None:
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> object:
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        return format_value(self._df.iat[index.row(), index.column()])

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> object:
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self._df.columns[section])
        return str(section + 1)


class ChartPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.figure = Figure(figsize=(10, 8), constrained_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.flow_ax = self.figure.add_subplot(3, 1, 1)
        self.level_ax = self.figure.add_subplot(3, 1, 2, sharex=self.flow_ax)
        self.storage_ax = self.figure.add_subplot(3, 1, 3, sharex=self.flow_ax)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def clear(self) -> None:
        for ax in [self.flow_ax, self.level_ax, self.storage_ax]:
            ax.clear()

    def _add_series(self, ax, name: str, df: pd.DataFrame, y_col: str, dashed: bool = False) -> None:
        if df is None or df.empty or y_col not in df or "datetime" not in df:
            return
        clean = df[["datetime", y_col]].copy()
        clean["datetime"] = pd.to_datetime(clean["datetime"], errors="coerce")
        clean[y_col] = pd.to_numeric(clean[y_col], errors="coerce")
        clean = clean.dropna()
        if clean.empty:
            return
        linestyle = "--" if dashed else "-"
        ax.plot(clean["datetime"], clean[y_col], label=name, linestyle=linestyle, linewidth=1.6)

    def update_plot(
        self,
        obs_df: pd.DataFrame,
        scenario_results: dict[str, dict[str, pd.DataFrame]],
        level_reference_df: pd.DataFrame,
    ) -> None:
        self.clear()
        self._add_series(self.flow_ax, "Qin", obs_df, "inflow_m3s")
        default_payload = scenario_results.get("default_outflow")
        default_source = default_payload.get("outflow_source") if isinstance(default_payload, dict) else None
        if default_source == "Qout_estimated_default" and isinstance(default_payload, dict):
            self._add_series(self.flow_ax, "Qout ước tính mặc định", default_payload["simulation"], "outflow_m3s")
        else:
            self._add_series(self.flow_ax, "Qout mặc định", obs_df, "outflow_m3s")
        for name, payload in scenario_results.items():
            sim = payload["simulation"]
            label = self._scenario_label(name)
            if name != "default_outflow":
                self._add_series(self.flow_ax, f"Qout {label}", sim, "outflow_m3s")
            self._add_series(self.level_ax, f"Mực nước {label}", sim, "water_level_m")
            self._add_series(self.storage_ax, f"Dung tích {label}", sim, "storage_mcm")
        if level_reference_df is not None and not level_reference_df.empty:
            for label, group in level_reference_df.dropna(subset=["level_m"]).groupby("level_label"):
                self._add_series(self.level_ax, str(label), group, "level_m", dashed=True)
            for label, group in level_reference_df.dropna(subset=["storage_mcm"]).groupby("storage_label"):
                self._add_series(self.storage_ax, str(label), group, "storage_mcm", dashed=True)

        self.flow_ax.set_title("Lưu lượng")
        self.flow_ax.set_ylabel("m3/s")
        self.level_ax.set_title("Mực nước")
        self.level_ax.set_ylabel("m")
        self.storage_ax.set_title("Dung tích")
        self.storage_ax.set_ylabel("triệu m3")
        self.storage_ax.set_xlabel("Thời gian")
        for ax in [self.flow_ax, self.level_ax, self.storage_ax]:
            ax.grid(True, color="#d9d9d9", linewidth=0.7)
            ax.legend(loc="best", fontsize=8)
        self.canvas.draw_idle()

    def _scenario_label(self, name: str) -> str:
        labels = {
            "default_outflow": "mặc định",
            "constant_outflow": "không đổi",
            "time_window_adjustment": "theo khoảng thời gian",
        }
        if name.startswith("multiplier_"):
            return "hệ số " + name.removeprefix("multiplier_").replace("_", ".")
        return labels.get(name, name.replace("_", " "))


class DashboardWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Bảng điều khiển vận hành hồ chứa")
        self.resize(1360, 860)
        self.uploaded_obs_df: pd.DataFrame | None = None
        self.last_results: dict[str, pd.DataFrame] = {}
        self._load_inputs()
        self._build_ui()
        self._populate_reservoirs()
        self.refresh_available_dates()

    def _load_inputs(self) -> None:
        self.reservoir_ids = load_reservoir_ids(DATA / "reservoir_id.csv")
        self.reservoir_parameters = load_reservoir_parameters(DATA / "reservoir_parameters.csv")
        self.level_constraints = load_level_constraints(DATA / "level_constraints.csv")

    def _build_ui(self) -> None:
        toolbar = self.addToolBar("Chính")
        upload_action = QAction("Tải CSV", self)
        upload_action.triggered.connect(self.load_uploaded_csv)
        toolbar.addAction(upload_action)
        export_action = QAction("Xuất CSV mô phỏng", self)
        export_action.triggered.connect(self.export_scenario_csv)
        toolbar.addAction(export_action)

        splitter = QSplitter()
        splitter.addWidget(self._build_controls())
        splitter.addWidget(self._build_tabs())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

    def _build_controls(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        form = QFormLayout()
        self.reservoir_combo = QComboBox()
        self.reservoir_combo.currentTextChanged.connect(self.refresh_available_dates)
        form.addRow("Hồ chứa", self.reservoir_combo)

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        form.addRow("Ngày bắt đầu", self.start_date)
        self.start_hour = QSpinBox()
        self.start_hour.setRange(0, 23)
        form.addRow("Giờ bắt đầu", self.start_hour)
        self.window_combo = QComboBox()
        self.window_combo.addItems(WINDOW_OPTIONS.keys())
        form.addRow("Cửa sổ thời gian", self.window_combo)
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        form.addRow("Ngày kết thúc tùy chỉnh", self.end_date)
        self.end_hour = QSpinBox()
        self.end_hour.setRange(0, 23)
        form.addRow("Giờ kết thúc tùy chỉnh", self.end_hour)

        self.custom_initial_check = QCheckBox("Dùng mực nước ban đầu tùy chỉnh")
        form.addRow(self.custom_initial_check)
        self.initial_level = QDoubleSpinBox()
        self.initial_level.setRange(-10000.0, 10000.0)
        self.initial_level.setDecimals(3)
        self.initial_level.setSingleStep(0.1)
        form.addRow("Mực nước ban đầu (m)", self.initial_level)

        self.default_outflow_source = QComboBox()
        self.default_outflow_source.addItem("Dùng outflow_m3s trong CSV", "observed")
        self.default_outflow_source.addItem("Ước tính Qout từ Qin và mực nước hồ", "estimated")
        form.addRow("Nguồn lưu lượng xả mặc định", self.default_outflow_source)

        self.scenario_combo = QComboBox()
        self.scenario_combo.addItems(SCENARIO_OPTIONS.keys())
        form.addRow("Kịch bản xả", self.scenario_combo)
        self.scenario_value = QDoubleSpinBox()
        self.scenario_value.setRange(0.0, 100000.0)
        self.scenario_value.setDecimals(3)
        self.scenario_value.setSingleStep(1.0)
        form.addRow("Giá trị / hệ số", self.scenario_value)
        self.scenario_start = QComboBox()
        form.addRow("Bắt đầu điều chỉnh", self.scenario_start)
        self.scenario_end = QComboBox()
        form.addRow("Kết thúc điều chỉnh", self.scenario_end)

        run_button = QPushButton("Chạy mô phỏng")
        run_button.clicked.connect(self.run_simulation)

        controls = QGroupBox("Điều khiển")
        controls.setLayout(form)
        layout.addWidget(controls)
        layout.addWidget(run_button)
        layout.addStretch(1)
        box.setMinimumWidth(310)
        return box

    def _build_tabs(self) -> QWidget:
        tabs = QTabWidget()
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        tabs.addTab(self.summary_text, "Thiết lập")
        self.chart_panel = ChartPanel()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.chart_panel)
        tabs.addTab(scroll, "Biểu đồ")

        self.comparison_model = DataFrameModel()
        self.comparison_table = QTableView()
        self.comparison_table.setModel(self.comparison_model)
        tabs.addTab(self.comparison_table, "So sánh kịch bản")

        self.diagnostics_model = DataFrameModel()
        self.diagnostics_table = QTableView()
        self.diagnostics_table.setModel(self.diagnostics_model)
        tabs.addTab(self.diagnostics_table, "Chẩn đoán dữ liệu")
        return tabs

    def _populate_reservoirs(self) -> None:
        names = self.reservoir_ids["reservoir_name_en"].dropna().astype(str).tolist()
        self.reservoir_combo.addItems(names)

    def load_uploaded_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Tải CSV quan trắc", str(ROOT), "CSV files (*.csv)")
        if not path:
            return
        try:
            df = pd.read_csv(path)
            self.uploaded_obs_df = clean_observed_timeseries_dataframe(df, self.reservoir_combo.currentText())
            self.refresh_available_dates()
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi CSV", str(exc))

    def export_scenario_csv(self) -> None:
        sim = self.last_results.get("custom_simulation")
        if sim is None:
            sim = self.last_results.get("baseline_simulation")
        if sim is None or sim.empty:
            QMessageBox.information(self, "Chưa có dữ liệu", "Hãy chạy mô phỏng trước khi xuất CSV.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Xuất CSV mô phỏng", str(ROOT / "scenario_simulation.csv"), "CSV files (*.csv)")
        if path:
            sim.to_csv(path, index=False)

    def _load_observed(self) -> tuple[pd.DataFrame, str]:
        if self.uploaded_obs_df is not None:
            return self.uploaded_obs_df.copy(), "uploaded CSV"
        df, source = load_clean_observed_timeseries(CSV_FOLDER, self.reservoir_combo.currentText())
        return df, str(source or "")

    def refresh_available_dates(self) -> None:
        try:
            obs_df, _ = self._load_observed()
        except Exception:
            return
        if obs_df.empty:
            return
        min_dt = pd.to_datetime(obs_df["datetime"]).min()
        max_dt = pd.to_datetime(obs_df["datetime"]).max()
        self.start_date.setDate(QDate(min_dt.year, min_dt.month, min_dt.day))
        self.end_date.setDate(QDate(max_dt.year, max_dt.month, max_dt.day))
        self.start_hour.setValue(int(min_dt.hour))
        self.end_hour.setValue(int(max_dt.hour))
        default_out = pd.to_numeric(obs_df.get("outflow_m3s", pd.Series(dtype=float)), errors="coerce").mean()
        self.scenario_value.setValue(float(default_out) if pd.notna(default_out) else 0.0)

    def _selected_window(self, obs_df: pd.DataFrame) -> pd.DataFrame:
        start = pd.Timestamp(
            self.start_date.date().toPython()
        ) + pd.Timedelta(hours=int(self.start_hour.value()))
        end = pd.Timestamp(self.end_date.date().toPython()) + pd.Timedelta(hours=int(self.end_hour.value()))
        return filter_time_window(obs_df, start, WINDOW_OPTIONS[self.window_combo.currentText()], end)

    def _sync_scenario_time_controls(self, selected_obs: pd.DataFrame) -> None:
        values = selected_obs["datetime"].astype(str).tolist()
        current_start = self.scenario_start.currentText()
        current_end = self.scenario_end.currentText()
        self.scenario_start.blockSignals(True)
        self.scenario_end.blockSignals(True)
        self.scenario_start.clear()
        self.scenario_end.clear()
        self.scenario_start.addItems(values)
        self.scenario_end.addItems(values)
        if current_start in values:
            self.scenario_start.setCurrentText(current_start)
        if current_end in values:
            self.scenario_end.setCurrentText(current_end)
        elif values:
            self.scenario_end.setCurrentIndex(len(values) - 1)
        self.scenario_start.blockSignals(False)
        self.scenario_end.blockSignals(False)

    def run_simulation(self) -> None:
        try:
            self._run_simulation()
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi mô phỏng", str(exc))

    def _run_simulation(self) -> None:
        reservoir_name = self.reservoir_combo.currentText()
        obs_df, source = self._load_observed()
        selected_obs = self._selected_window(obs_df)
        if selected_obs.empty:
            raise ValueError("Không có dòng chuỗi thời gian quan trắc trong cửa sổ đã chọn.")
        hypsometry_df, hypsometry_source = load_hypsometry(DATA / "AEV_obs", reservoir_name)
        if hypsometry_df.empty:
            raise ValueError("Không có tệp đường quan hệ AEV cho hồ chứa đã chọn.")
        selected_obs, default_outflow_source, default_outflow_label = prepare_default_outflow_inputs(
            selected_obs,
            hypsometry_df,
            self.default_outflow_source.currentData(),
        )
        self._sync_scenario_time_controls(selected_obs)

        parameter_rows = parameters_for_reservoir(self.reservoir_parameters, reservoir_name)
        initial_level, _, exact_initial = get_initial_water_level(selected_obs)
        if self.custom_initial_check.isChecked():
            initial_level = float(self.initial_level.value())
            exact_initial = True
        elif pd.notna(initial_level):
            self.initial_level.setValue(float(initial_level))
        else:
            raise ValueError("Không có mực nước ban đầu hợp lệ. Hãy bật tùy chọn mực nước ban đầu tùy chỉnh và nhập giá trị.")

        window_end = get_window_end_datetime(selected_obs)
        active_rows = get_active_constraints_for_window_end(self.level_constraints, reservoir_name, window_end, "Auto")
        active_season, active_seasons = active_season_from_rows(active_rows)
        if selected_obs["inflow_m3s"].isna().all() or default_outflow_values(selected_obs, default_outflow_source)[0].isna().all():
            raise ValueError("Thiếu lưu lượng đến hoặc lưu lượng xả mặc định. Hãy cung cấp outflow_m3s trong CSV hoặc inflow_m3s và water_level_m.")
        baseline_outflow = make_default_outflow(selected_obs, default_outflow_source)
        baseline_sim = simulate_reservoir(selected_obs, baseline_outflow, initial_level, hypsometry_df, parameter_rows)
        capacity_targets = derive_reservoir_capacity_targets(parameter_rows, hypsometry_df, pd.DataFrame(), active_season)
        baseline_metrics = calculate_end_of_window_capacity_metrics(
            baseline_sim, selected_obs, capacity_targets, active_season
        )

        scenario_type = SCENARIO_OPTIONS[self.scenario_combo.currentText()]
        if scenario_type == "constant":
            custom_outflow = make_constant_outflow(selected_obs, self.scenario_value.value())
        elif scenario_type == "multiplier":
            custom_outflow = make_multiplier_outflow(selected_obs, self.scenario_value.value(), default_outflow_source)
        elif scenario_type == "time_window":
            custom_outflow = make_time_window_outflow(
                selected_obs,
                self.scenario_start.currentText(),
                self.scenario_end.currentText(),
                self.scenario_value.value(),
                default_outflow_source,
            )
        else:
            custom_outflow = baseline_outflow

        custom_name = custom_outflow["scenario_name"].iloc[0]
        custom_sim = simulate_reservoir(selected_obs, custom_outflow, initial_level, hypsometry_df, parameter_rows)
        scenario_results = {
            "default_outflow": {"simulation": baseline_sim, "obs_df": selected_obs, "outflow_source": default_outflow_label},
            custom_name: {"simulation": custom_sim, "obs_df": selected_obs},
        }
        if custom_name == "default_outflow":
            scenario_results = {
                "default_outflow": {"simulation": baseline_sim, "obs_df": selected_obs, "outflow_source": default_outflow_label}
            }
        level_reference_df = build_parameter_level_reference_series(custom_sim, parameter_rows, active_season, hypsometry_df)
        comparison = compare_scenarios(scenario_results, pd.DataFrame(), capacity_targets)

        self.chart_panel.update_plot(selected_obs, scenario_results, level_reference_df)
        self.comparison_model.set_dataframe(comparison)
        self.diagnostics_model.set_dataframe(selected_obs.head(100))
        self.last_results = {
            "baseline_simulation": baseline_sim,
            "custom_simulation": custom_sim,
            "selected_observed": selected_obs,
            "custom_outflow": custom_outflow,
        }
        self.summary_text.setPlainText(
            self._summary_text(
                reservoir_name,
                source,
                str(hypsometry_source or ""),
                selected_obs,
                initial_level,
                exact_initial,
                active_seasons,
                default_outflow_label,
                baseline_metrics,
                baseline_sim,
                custom_sim,
            )
        )

    def _summary_text(
        self,
        reservoir_name: str,
        source: str,
        hypsometry_source: str,
        selected_obs: pd.DataFrame,
        initial_level: float,
        exact_initial: bool,
        active_seasons: list[str],
        default_outflow_label: str,
        metrics: dict[str, object],
        baseline_sim: pd.DataFrame,
        custom_sim: pd.DataFrame,
    ) -> str:
        baseline_limits = summarize_physical_limit_violations(baseline_sim)
        custom_limits = summarize_physical_limit_violations(custom_sim)
        lines = [
            f"Hồ chứa: {reservoir_name}",
            f"Nguồn chuỗi quan trắc: {source}",
            f"Nguồn đường quan hệ AEV: {hypsometry_source}",
            f"Cửa sổ đã chọn: {selected_obs['datetime'].min()} đến {selected_obs['datetime'].max()}",
            f"Số dòng dữ liệu: {len(selected_obs)}",
            f"Mực nước ban đầu: {initial_level:,.3f} m",
            f"Mực nước ban đầu đúng tại thời điểm đầu CSV: {'Có' if exact_initial else 'Không'}",
            f"Mùa đang áp dụng: {', '.join(active_seasons) if active_seasons else 'không có dữ liệu'}",
            "",
            f"Mực nước cuối kỳ: {baseline_sim['water_level_m'].iloc[-1]:,.3f} m",
            f"Dung tích cuối kỳ: {baseline_sim['storage_mcm'].iloc[-1]:,.3f} triệu m3",
            f"Loại dung tích mục tiêu: {metrics.get('capacity_target_type', 'không có dữ liệu')}",
            f"Tỷ lệ dung tích đã dùng: {format_value(metrics.get('capacity_used_pct'))}%",
            f"Dung tích còn lại: {format_value(metrics.get('remaining_storage_mcm'))} triệu m3",
            f"Số ngày để đầy theo lưu lượng đến trung bình: {format_value(metrics.get('days_to_fill_from_inflow_only'))}",
        ]
        if default_outflow_label == "Qout_estimated_default":
            lines += [
                "",
                "Lưu lượng xả mặc định được ước tính từ lưu lượng đến và mực nước hồ bằng cân bằng khối lượng.",
            ]
            negative_count = int(selected_obs.get("negative_outflow_flag", pd.Series(dtype=bool)).fillna(False).sum())
            if negative_count:
                lines += [
                    "Cảnh báo: lưu lượng xả ước tính có giá trị âm và không bị cắt về 0.",
                    "Nguyên nhân có thể là lưu lượng đến bị đánh giá thấp, mực nước nhiễu, sai đường AEV, thiếu mưa trực tiếp trên mặt hồ, lệch timestamp, hoặc lỗi chất lượng dữ liệu.",
                ]
        if baseline_limits:
            lines += ["", "Cảnh báo giới hạn vật lý của mô phỏng cơ sở:", str(baseline_limits)]
        if custom_limits:
            lines += ["", "Cảnh báo giới hạn vật lý của kịch bản:", str(custom_limits)]
        return "\n".join(lines)


def main() -> int:
    app = QApplication(sys.argv)
    window = DashboardWindow()
    if "--smoke-test" in sys.argv:
        window._run_simulation()
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        log_path = Path(sys.argv[0]).resolve().with_name("desktop_gui_error.log")
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        raise
