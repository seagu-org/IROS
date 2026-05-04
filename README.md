# Dashboard vận hành hồ thủy điện

Dashboard này hỗ trợ xem dữ liệu lưu lượng đến, lưu lượng xả, mực nước, dung tích mô phỏng và so sánh các kịch bản xả cho từng hồ chứa. Repo có hai cách chạy chính:

- Chạy trực tiếp bằng Streamlit để phát triển, kiểm tra dữ liệu và dùng nội bộ.
- Build bản desktop `.exe` khi cần gửi cho người dùng không làm việc trực tiếp với Python/source code.

## 1. Cấu trúc quan trọng

```text
reservoir_dashboard/app.py        # Ứng dụng Streamlit
reservoir_dashboard/src/          # Module đọc dữ liệu, mô phỏng, vẽ biểu đồ
run_dashboard.py                  # Launcher chạy Streamlit bằng Python
run_desktop_dashboard.py          # GUI desktop PySide6
build_desktop_exe.cmd             # Lệnh build exe trên Windows
build_desktop_exe.ps1             # Script build exe bằng Nuitka
requirements.txt                  # Phụ thuộc cho Streamlit
requirements-desktop.txt          # Phụ thuộc cho GUI desktop/exe
environment-desktop.yml           # Môi trường Conda khuyến nghị cho build exe
data/                             # Dữ liệu bắt buộc khi chạy dashboard
```

## 2. Dữ liệu đầu vào

Các file/thư mục sau cần có trong `data/`:

- `data/reservoir_id.csv`: danh sách hồ chứa, cần cột `reservoir_name_en`.
- `data/reservoir_parameters.csv`: thông số hồ chứa, dùng các cột `reservoir_name_en`, `parameter_name`, `value`, `unit`.
- `data/level_constraints.csv`: thông tin mùa và ràng buộc mực nước.
- `data/AEV_obs/`: đường quan hệ cao trình - diện tích - dung tích của từng hồ.
- `data/Q/csv/`: chuỗi thời gian đã làm sạch cho từng hồ.

CSV chuỗi thời gian trong `data/Q/csv/` cần có tối thiểu:

- `datetime`
- `inflow_m3s`

Để mô phỏng lưu lượng xả mặc định, CSV cần có một trong hai nhóm dữ liệu:

- `outflow_m3s`: dùng trực tiếp làm lưu lượng xả mặc định trong CSV.
- Hoặc `water_level_m` cùng với `inflow_m3s`: dashboard sẽ ước tính lưu lượng xả mặc định bằng cân bằng khối lượng hồ chứa.

Các cột nên có thêm:

- `reservoir_name_en`
- `water_level_m`

Trong Streamlit, người dùng có thể tải lên một CSV riêng cho phiên chạy hiện tại. File tải lên không ghi đè dữ liệu trong `data/Q/csv/`.

## 3. Ước tính lưu lượng xả khi thiếu `outflow_m3s`

Nếu `outflow_m3s` bị thiếu nhưng có `inflow_m3s`, `water_level_m`, và đường quan hệ AEV, dashboard sẽ tính:

```text
estimated_outflow_m3s = inflow_m3s - storage_change_m3 / dt_seconds
```

Trong đó dung tích `storage_m3` được nội suy từ `water_level_m` theo AEV, `storage_change_m3 = storage_t - storage_t_minus_1`, và `dt_seconds` lấy từ khoảng cách giữa hai thời điểm liên tiếp.

Chuỗi này được ghi nhãn rõ là `Qout ước tính mặc định`, không được xem là `outflow_m3s` quan trắc. Dữ liệu đầu ra có thêm các cờ:

- `negative_outflow_flag`
- `outside_reasonable_range_flag`
- `missing_water_level_flag`
- `missing_inflow_flag`

Nếu giá trị ước tính âm, dashboard giữ nguyên giá trị và hiển thị cảnh báo. Không tự động cắt về 0 vì giá trị âm có thể chỉ ra lưu lượng đến bị đánh giá thấp, mực nước nhiễu, sai đường AEV, thiếu mưa trực tiếp trên mặt hồ, lệch timestamp, hoặc vấn đề chất lượng dữ liệu.

## 4. Chạy dashboard bằng Streamlit

Từ thư mục gốc repo, tạo và kích hoạt môi trường Python. Trên Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Chạy dashboard:

```powershell
streamlit run reservoir_dashboard/app.py
```

Hoặc chạy qua launcher của repo:

```powershell
python run_dashboard.py
```

Sau khi chạy, mở địa chỉ Streamlit hiển thị trong terminal, thường là:

```text
http://localhost:8501
```

## 5. Chạy GUI desktop khi chưa build exe

Dùng cách này để kiểm tra giao diện desktop trước khi đóng gói:

```powershell
conda env create -f environment-desktop.yml
conda activate reservoir_desktop
python run_desktop_dashboard.py
```

Nếu môi trường `reservoir_desktop` đã tồn tại:

```powershell
conda activate reservoir_desktop
python run_desktop_dashboard.py
```

## 6. Build file exe mới

Build exe khi đã kiểm tra GUI desktop chạy đúng:

```powershell
conda activate reservoir_desktop
.\build_desktop_exe.cmd -Clean
```

Kết quả mặc định:

```text
dist\ReservoirDashboardDesktop\ReservoirDashboardDesktop.exe
```

Khi gửi cho người dùng, gửi toàn bộ thư mục:

```text
dist\ReservoirDashboardDesktop
```

Không chỉ gửi riêng file `.exe`, vì bản desktop cần các thư viện và dữ liệu đi kèm trong cùng thư mục.

Nếu thật sự cần bản một file duy nhất, có thể build thêm:

```powershell
.\build_desktop_exe.cmd -Clean -OneFile
```

Chỉ dùng `-OneFile` sau khi bản thư mục `dist\ReservoirDashboardDesktop` đã chạy ổn trên máy đích.

## 7. Khi nào cần build lại exe

Cần build lại exe khi có thay đổi trong:

- `run_desktop_dashboard.py`
- `reservoir_dashboard/src/`
- `data/` nếu muốn dữ liệu mới được đóng gói sẵn trong bản gửi đi
- `requirements-desktop.txt` hoặc `environment-desktop.yml`
- `build_desktop_exe.ps1` hoặc `build_desktop_exe.cmd`

Không cần build lại exe nếu chỉ chạy thử Streamlit trên máy phát triển bằng source hiện tại.

Xem hướng dẫn chi tiết hơn tại [HUONG_DAN_TAO_CAP_NHAT_EXE.md](HUONG_DAN_TAO_CAP_NHAT_EXE.md).

## 8. Dọn file build/cache

Các thư mục/file build như `build/`, `dist/`, `.nuitka-cache/`, `_MEI*/`, `*.exe`, `*.log`, `nuitka-crash-report.xml` là artifact cục bộ và không cần commit. Khi muốn build lại sạch, dùng:

```powershell
.\build_desktop_exe.cmd -Clean
```

Nếu cần dọn thủ công, chỉ xóa các artifact đã được liệt kê trong `.gitignore`, không xóa `data/`, `reservoir_dashboard/`, `run_desktop_dashboard.py`, hoặc các file `requirements*.txt`.
