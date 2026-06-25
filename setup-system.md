# Hướng dẫn cài đặt môi trường Python

Tài liệu này mô tả cách thiết lập môi trường phát triển Python cho dự án
**Stock-trend-forecasting-system** trên Linux (đã thử nghiệm trên Ubuntu 24.04+).

## 1. Yêu cầu hệ thống

- **Python**: 3.10 trở lên (đã thử nghiệm với 3.14.4)
- **pip**: phiên bản đi kèm hệ thống (>= 25)
- **venv**: module tạo môi trường ảo chuẩn của Python
- **Git**: để clone repository

## 2. Cài đặt Python, pip và venv (Ubuntu/Debian)

Trên các bản Linux mới, `pip` và `venv` thường không được cài sẵn. Cài bằng:

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv
```

Kiểm tra sau khi cài:

```bash
python3 --version        # Python 3.x.x
python3 -m pip --version # pip 25.x hoặc mới hơn
python3 -m venv --help   # hướng dẫn sử dụng venv
```

## 3. Clone và cài đặt project

```bash
git clone <repository-url> Stock-trend-forecasting-system
cd Stock-trend-forecasting-system
```

## 4. Tạo và kích hoạt virtual environment

Tạo môi trường ảo trong thư mục `.venv` ngay tại project:

```bash
python3 -m venv .venv
```

Kích hoạt môi trường ảo:

```bash
# bash / zsh
source .venv/bin/activate

# fish
source .venv/bin/activate.fish

# csh / tcsh
source .venv/bin/activate.csh

# PowerShell
.venv\Scripts\Activate.ps1
```

Sau khi kích hoạt, prompt sẽ có tiền tố `(.venv)`.

## 5. Nâng cấp pip và cài đặt dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Các package chính được cài:

| Package       | Mục đích                                  |
| ------------- | ----------------------------------------- |
| pandas        | Xử lý dữ liệu dạng bảng                  |
| numpy         | Tính toán số học                          |
| scikit-learn  | Mô hình ML cơ bản                         |
| streamlit     | Dashboard tương tác                       |
| plotly        | Biểu đồ tương tác                         |
| pytest        | Chạy unit test                            |

## 6. Kiểm tra cài đặt

Chạy test mẫu để chắc chắn mọi thứ hoạt động:

```bash
pytest tests/
```

Kết quả mong đợi:

```
============================= test session starts ==============================
collected 1 item

tests/test_scaffold.py::test_scaffold_is_ready PASSED                    [100%]

============================== 1 passed in 0.02s ===============================
```

## 7. Các lệnh thường dùng

```bash
# Chạy pipeline chính
python -m src.pipeline

# Chạy dashboard Streamlit
streamlit run src/dashboard.py

# Chạy toàn bộ test
pytest tests/

# Chạy test với verbose
pytest tests/ -v

# Chạy test với coverage
pytest tests/ --cov=src
```

## 8. Vô hiệu hóa và xoá môi trường ảo

Tạm thoát khỏi môi trường ảo:

```bash
deactivate
```

Xoá hoàn toàn môi trường ảo (khi cần cài lại từ đầu):

```bash
rm -rf .venv
```

Thư mục `.venv/` đã được thêm vào `.gitignore`, không bị commit lên git.

## 9. Khắc phục sự cố

| Vấn đề                                              | Cách xử lý                                                                 |
| --------------------------------------------------- | -------------------------------------------------------------------------- |
| `No module named pip` sau khi tạo venv               | Đảm bảo đã chạy `sudo apt-get install python3-pip` trước khi tạo venv       |
| `ensurepip is not available`                        | Cài `python3-venv` (`sudo apt-get install python3-venv`)                   |
| Một số package không có wheel cho Python quá mới     | Dùng Python 3.12 hoặc 3.11 thay thế (đã thử nghiệm ổn định)               |
| Lỗi quyền khi cài pip global                        | Luôn cài đặt trong `.venv`, không dùng `pip` ngoài môi trường ảo            |
| `streamlit` không nhận diện được `src/`              | Chạy từ thư mục gốc của dự án, hoặc thêm `PYTHONPATH=src`                  |

## 10. Cấu trúc thư mục sau khi cài đặt

```text
Stock-trend-forecasting-system/
├── .venv/                  # Môi trường ảo (không commit)
├── data/                   # Dataset mẫu
├── src/                    # Mã nguồn chính
├── tests/                  # Unit test
├── outputs/                # Kết quả chạy pipeline
├── openspec/               # Tài liệu OpenSpec
├── requirements.txt        # Danh sách dependency
├── setup-system.md         # File hướng dẫn này
└── README.md
```

## Ghi chú

- Luôn kích hoạt `.venv` trước khi chạy bất kỳ lệnh Python nào trong project.
- Khi thêm package mới, cập nhật `requirements.txt` bằng
  `pip freeze > requirements.txt` sau khi đã verify package hoạt động.
- Không commit thư mục `.venv/` lên git (đã được `.gitignore` xử lý).
