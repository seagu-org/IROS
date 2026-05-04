# Bảng điều khiển vận hành hồ thủy điện

Dự án này cung cấp dashboard Streamlit để người vận hành hồ thủy điện kiểm tra lưu lượng đến quan trắc hoặc dự báo, lưu lượng xả mặc định, dung tích mô phỏng, mực nước mô phỏng, mùa đang áp dụng, các đường tham chiếu mực nước và dung tích theo thông số hồ chứa, cùng các kịch bản xả có thể chỉnh sửa.

## Tệp đầu vào bắt buộc

- `data/reservoir_id.csv`
  - Cột bắt buộc: `reservoir_name_en`
- `data/reservoir_parameters.csv`
  - Dùng `reservoir_name_en`, `parameter_name`, `value`, và `unit` khi có.
- `data/AEV_obs/`
  - Các tệp đường quan hệ AEV của hồ chứa. Các cột kỳ vọng là `CaoTrinh_m`, `Dientich_km2`, và `Dungtich_10^6m3`.
- `data/level_constraints.csv`
  - Các cột kỳ vọng: `regulation_id`, `reservoir_name_en`, `season`, `period_start_mmdd`, `period_end_mmdd`, `constraint_type`, `level_min_m`, `level_max_m`, `article_ref`.
- `data/Q/2025/<reservoir_name_en>.xlsx`
  - Các cột chuỗi thời gian kỳ vọng: ngày, giờ, lưu lượng đến, lưu lượng xả, và mực nước.

## Cột chuỗi thời gian đã làm sạch

Các tệp Excel được chuyển thành `data/Q/csv/<reservoir_name_en>.csv` với tên cột ASCII ổn định:

- `datetime`
- `date`
- `hour`
- `reservoir_name_en`
- `inflow_m3s`
- `outflow_m3s`
- `water_level_m`

Các dòng có cột giờ chứa `TB` được loại bỏ vì đó là dòng trung bình, không phải dòng mô phỏng theo giờ.

Notebook không dùng GUI và các ví dụ script đọc trực tiếp từ `data/Q/csv/`. Với một thời kỳ mới, hãy cập nhật các CSV đã làm sạch trong thư mục đó. Nếu tệp Excel nguồn thay đổi, hãy chạy lại script chuyển đổi trước khi chạy notebook.

Trong dashboard, người dùng cũng có thể tải lên CSV riêng cho một lần chạy từ thanh bên. CSV tải lên chỉ được dùng trong phiên Streamlit hiện tại và không ghi đè tệp trong `data/Q/csv/`. Tệp tải lên phải có:

- `datetime`
- `inflow_m3s`
- `outflow_m3s`

Các cột tùy chọn:

- `reservoir_name_en`
- `water_level_m`

## Chuyển Excel sang CSV

Từ thư mục gốc của repository:

```bash
python reservoir_dashboard/scripts/convert_q_2025_excel_to_csv.py
```

Dashboard không còn hiển thị điều khiển tạo lại CSV trong giao diện. Hãy dùng script trên khi dữ liệu Excel đầu vào thay đổi.

## Chạy dashboard

Cài đặt các thư viện phụ thuộc trong môi trường Python:

```bash
pip install streamlit pandas numpy plotly openpyxl pytest
```

Chạy:

```bash
streamlit run reservoir_dashboard/app.py
```

## Chạy GUI desktop

Nếu Streamlit khó đóng gói thành `.exe`, có thể dùng GUI desktop PySide6:

```bash
pip install -r requirements-desktop.txt
python run_desktop_dashboard.py
```

Khuyến nghị dùng môi trường Conda riêng cho GUI desktop để tránh xung đột Qt trong môi trường nghiên cứu hiện tại:

```powershell
conda env create -f environment-desktop.yml
conda activate reservoir_desktop
python run_desktop_dashboard.py
```

GUI desktop dùng lại các module mô phỏng trong `reservoir_dashboard/src`, đọc dữ liệu từ `data/`, hỗ trợ chọn hồ chứa, cửa sổ thời gian, mực nước ban đầu, kịch bản xả cơ bản, biểu đồ Qin/Qout/mực nước/dung tích, bảng so sánh kịch bản, tải CSV quan trắc riêng, và xuất CSV mô phỏng.

Để build `.exe` bằng Nuitka:

```powershell
.\build_desktop_exe.ps1
```

File đầu ra mặc định là `ReservoirDashboardDesktop.exe`. Cách này không phân phối source `.py` trực tiếp như chạy Streamlit, nhưng không phải cơ chế bảo vệ tuyệt đối trước reverse engineering.

## Cửa sổ thời gian đã chọn

Người vận hành chọn hồ chứa, thời điểm bắt đầu, và một trong các độ dài:

- 24 giờ
- 48 giờ
- 72 giờ
- 1 tuần
- 2 tuần
- thời điểm kết thúc tùy chỉnh

Cửa sổ dữ liệu đã chọn được dùng cho lưu lượng đến, lưu lượng xả mặc định, mực nước ban đầu, mô phỏng, chỉ số, so sánh kịch bản, và chọn mùa. Các tab thiết lập và chẩn đoán cũng hiển thị thời kỳ mô phỏng khả dụng trong tệp CSV đã làm sạch của hồ chứa đã chọn.

## Giai đoạn 1: mô phỏng cơ sở

Mô phỏng cơ sở dùng lưu lượng xả mặc định và phương trình cân bằng khối lượng:

```text
S_next = S_current + (Q_in - Q_out) * dt_seconds
```

Dung tích ban đầu được suy ra từ mực nước hợp lệ đầu tiên trong cửa sổ đã chọn bằng đường quan hệ AEV của hồ chứa. Dung tích được lưu nội bộ theo mét khối và hiển thị theo triệu mét khối khi phù hợp.

Trong thanh bên dashboard, người dùng có thể chọn mực nước ban đầu lấy từ CSV hoặc nhập giá trị tùy chỉnh. Với các lần chạy không dùng GUI, đặt `custom_initial_water_level_m` trong `non_GUI.ipynb` hoặc ví dụ script để ghi đè mực nước ban đầu suy ra từ CSV cho một lần chạy cụ thể.

Nếu cân bằng khối lượng làm dung tích vượt ngoài miền vật lý của đường AEV, mô phỏng sẽ giới hạn dung tích và mực nước tại biên AEV. Đầu ra giữ `unbounded_storage_m3` để chẩn đoán và đánh dấu các dòng bị ảnh hưởng bằng `physical_limit_violation=True`, `physical_limit_type`, và `physical_limit_excess_mcm`.

## Giai đoạn 2: chỉnh sửa kịch bản

Tab kịch bản hỗ trợ:

- lưu lượng xả mặc định
- lưu lượng xả không đổi
- lưu lượng xả theo hệ số nhân
- lưu lượng xả thay thế trong một khoảng thời gian đã chọn
- chỉnh sửa lưu lượng xả thủ công bằng `st.data_editor`

Ứng dụng so sánh mô phỏng cơ sở và kịch bản tùy chỉnh đã chọn cạnh nhau bằng các chỉ số tóm tắt và các tệp CSV có thể tải xuống. So sánh kịch bản bao gồm `hours_to_fill_from_average_inflow` và `days_to_fill_from_average_inflow`.

## Biểu đồ và chú giải

Dashboard dùng ba biểu đồ con đồng bộ:

- Lưu lượng: các chuỗi `Qin`, `Qout_default`, và `Qout_<scenario>` tùy chỉnh.
- Mực nước: các chuỗi `WL_default` và `WL_<scenario>` tùy chỉnh.
- Dung tích: các chuỗi `V_default` và `V_<scenario>` tùy chỉnh.

Với mỗi kịch bản, Qout, WL, và V dùng cùng một màu đường. Nội dung hover ngắn gọn và chỉ hiển thị ngày cùng giá trị cho đường gần nhất. Các đường tham chiếu ngang không hiển thị hover.

## Chọn mùa và mực nước tham chiếu

Mùa đang áp dụng được chọn tự động theo thời điểm cuối cùng của cửa sổ mô phỏng đã chọn. Ứng dụng chuyển thời điểm đó sang `mmdd` và lọc các dòng giai đoạn mùa của hồ chứa đã chọn để lấy những dòng có giai đoạn chứa `mmdd`. Dashboard không có bộ chọn chế độ mùa hiển thị.

Biểu đồ mực nước vẽ các đường tham chiếu ngang từ `reservoir_parameters.csv` khi có các thuộc tính đó. Biểu đồ dung tích vẽ các đường tham chiếu dung tích tương ứng bằng đường quan hệ AEV. Nếu không có mực nước phù hợp, các thuộc tính dung tích trực tiếp như `total_storage_at_nwl` hoặc `dead_storage` được dùng khi phù hợp.

Trong mùa lũ, ứng dụng cố gắng vẽ:

- `normal_water_level` - Mực nước dâng bình thường
- `dead_water_level` - Mực nước chết
- `design_flood_level` - Mực nước lũ thiết kế
- `flood_check_level` - Mực nước lũ kiểm tra

Trong mùa cạn, ứng dụng cố gắng vẽ:

- `normal_water_level` - Mực nước dâng bình thường
- `dead_water_level` - Mực nước chết

Ứng dụng hiện không kiểm tra vi phạm ràng buộc mực nước.

## Hạn chế đã biết

- Chưa triển khai tối ưu hóa.
- Ứng dụng phụ thuộc vào các tệp đầu vào tường minh và không tự suy luận quy tắc mùa hoặc mực nước thông số bị thiếu.
- Nếu hồ chứa không có đường quan hệ AEV, mô phỏng bị tắt cho hồ chứa đó.
- Nếu môi trường thiếu `openpyxl`, chuyển đổi Excel sang CSV không thể chạy cho đến khi cài đặt gói đó.
