# Hướng dẫn tạo và cập nhật file exe

Tài liệu này mô tả khi nào cần tạo/cập nhật file `.exe` và quy trình build bản desktop cho dashboard hồ chứa.

## 1. Khi nào cần tạo file exe

Tạo file exe khi cần gửi dashboard cho người dùng không muốn cài Python hoặc không cần xem source code. Bản exe phù hợp cho:

- Máy vận hành nội bộ.
- Máy dùng để demo nhanh.
- Người dùng chỉ cần mở chương trình và làm việc với giao diện desktop.

Nếu đang phát triển, kiểm tra thuật toán, sửa dữ liệu hoặc debug giao diện, nên chạy Streamlit hoặc chạy `python run_desktop_dashboard.py` trước.

## 2. Khi nào cần cập nhật exe

Cần build lại exe sau mỗi thay đổi ảnh hưởng đến bản desktop:

- Sửa logic mô phỏng trong `reservoir_dashboard/src/`.
- Sửa giao diện desktop trong `run_desktop_dashboard.py`.
- Cập nhật dữ liệu trong `data/` và muốn dữ liệu mới đi kèm bản phát hành.
- Thêm, xóa hoặc đổi phiên bản thư viện trong `requirements-desktop.txt`.
- Đổi môi trường build trong `environment-desktop.yml`.
- Sửa script build `build_desktop_exe.ps1` hoặc `build_desktop_exe.cmd`.

Không cần build lại exe nếu chỉ sửa README, tài liệu, hoặc chỉ chạy Streamlit trên máy phát triển.

## 3. Chuẩn bị môi trường build

Khuyến nghị dùng Conda để tách môi trường desktop khỏi môi trường nghiên cứu khác:

```powershell
conda env create -f environment-desktop.yml
conda activate reservoir_desktop
```

Nếu môi trường đã tồn tại, chỉ cần kích hoạt:

```powershell
conda activate reservoir_desktop
```

Kiểm tra GUI desktop trước khi build:

```powershell
python run_desktop_dashboard.py
```

Chỉ build exe sau khi giao diện desktop chạy đúng với dữ liệu hiện tại.

## 4. Build bản thư mục khuyến nghị

Từ thư mục gốc repo:

```powershell
conda activate reservoir_desktop
.\build_desktop_exe.cmd -Clean
```

Kết quả:

```text
dist\ReservoirDashboardDesktop\ReservoirDashboardDesktop.exe
```

Khi gửi cho người dùng, gửi toàn bộ thư mục:

```text
dist\ReservoirDashboardDesktop
```

Không gửi riêng file `ReservoirDashboardDesktop.exe`, vì chương trình cần các file thư viện và dữ liệu nằm cùng thư mục.

## 5. Build bản một file

Bản một file có thể tiện gửi đi, nhưng dễ gặp lỗi giải nén tạm thời hoặc lỗi thư viện Qt trên một số máy Windows. Chỉ dùng sau khi bản thư mục đã chạy ổn:

```powershell
.\build_desktop_exe.cmd -Clean -OneFile
```

Kết quả:

```text
dist\ReservoirDashboardDesktop.exe
```

## 6. Kiểm tra sau khi build

Sau khi build xong:

1. Mở `dist\ReservoirDashboardDesktop\ReservoirDashboardDesktop.exe`.
2. Chọn hồ chứa và cửa sổ thời gian có dữ liệu.
3. Chạy mô phỏng mặc định.
4. Kiểm tra biểu đồ lưu lượng, mực nước, dung tích.
5. Thử xuất CSV mô phỏng.
6. Nếu dữ liệu thiếu `outflow_m3s` nhưng có `inflow_m3s` và `water_level_m`, kiểm tra chương trình dùng `Qout ước tính mặc định` và hiển thị thông báo: `Lưu lượng xả mặc định được ước tính từ lưu lượng đến và mực nước hồ bằng cân bằng khối lượng.`
7. Nếu có giá trị xả ước tính âm, xác nhận giá trị không bị cắt về 0 và cảnh báo dữ liệu được hiển thị.
8. Nếu cần gửi cho máy khác, copy toàn bộ `dist\ReservoirDashboardDesktop` sang máy đó và chạy lại kiểm tra nhanh.

## 7. File không cần giữ sau build

Các file/thư mục sau là artifact cục bộ, có thể xóa hoặc để script `-Clean` tạo lại:

- `build/`
- `dist/`
- `.nuitka-cache/`
- `_MEI*/`
- `*.build/`
- `*.dist/`
- `*.onefile-build/`
- `*.exe`
- `*.log`
- `nuitka-crash-report.xml`

Không xóa các file/thư mục sau vì chúng cần cho lần build tiếp theo:

- `data/`
- `reservoir_dashboard/`
- `run_desktop_dashboard.py`
- `build_desktop_exe.ps1`
- `build_desktop_exe.cmd`
- `requirements-desktop.txt`
- `environment-desktop.yml`
