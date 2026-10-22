# Website quản lý Phòng thí nghiệm Điện tử số

Ứng dụng Flask và SQLite chạy trên máy cá nhân để quản lý kho, mượn trả, chữ ký xác nhận dạng tên, QR thiết bị, cảnh báo tồn thấp và báo cáo CSV. Dữ liệu SQLite nằm trong thư mục `instance/`, không nằm trong kho mã nguồn.

## Cài đặt trên Windows

Mở PowerShell tại thư mục này và chạy:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:ADMIN_USERNAME = "admin"
$env:ADMIN_PASSWORD = "ThayBangMatKhauRiengDaiHon10KyTu"
$env:FLASK_SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
python app.py
```

Mở `http://127.0.0.1:5000`. Lần chạy đầu tạo tài khoản quản trị nếu đặt `ADMIN_USERNAME` và `ADMIN_PASSWORD`. Không dùng lại mật khẩu mẫu ở trên. Tạo thêm tài khoản từ trang tổng quan. Hãy sao lưu `instance/lab.sqlite3` định kỳ.

## Vai trò

- Quản trị viên: quản lý tài khoản, kho, mượn trả và báo cáo.
- Cán bộ: quản lý kho, lập phiếu và nhận thiết bị trả.
- Giảng viên: lập phiếu mượn.
- Sinh viên: xem kho và các phiếu mượn hiện tại.

## Lưu ý hiện trạng

Chữ ký hiện lưu dưới dạng tên được nhập để xác nhận, chưa phải chữ ký điện tử vẽ trên màn hình. QR chứa mã và tên thiết bị để nhận dạng. Ứng dụng hiện lưu dữ liệu và chạy nội bộ; chưa cấu hình máy chủ Internet, kho tệp ảnh/biên bản riêng, HTTPS hoặc sao lưu tự động. Giữ `.env`, mật khẩu và cơ sở dữ liệu ngoài repository.
