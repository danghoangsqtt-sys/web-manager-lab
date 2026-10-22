# Website quản lý Phòng thí nghiệm Điện tử số

Ứng dụng Flask và SQLite với giao diện gọn theo phong cách Notion. Khách xem kho, ảnh thiết bị, mã QR, số liệu và phiếu mượn mà không cần đăng nhập. Chỉ admin mới được thêm mặt hàng, tải ảnh, lập phiếu và xác nhận trả.

## Chạy thử trên Windows

Mở PowerShell tại thư mục dự án:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:ADMIN_USERNAME = "admin"
$env:ADMIN_PASSWORD = "ThayBangMatKhauRieng"
$env:FLASK_SECRET_KEY = (python -c "import secrets; print(secrets.token_hex(32))")
python app.py
```

Mở `http://127.0.0.1:5000`. Khách truy cập trang chủ trực tiếp. Admin quản trị tại `http://127.0.0.1:5000/login`. Lần chạy đầu, ứng dụng tạo admin khi có `ADMIN_USERNAME` và `ADMIN_PASSWORD`.

## Dữ liệu

- SQLite mặc định lưu ở `instance/lab.sqlite3`.
- Ảnh tải lên lưu tại `instance/uploads/`; hỗ trợ PNG, JPG, WEBP và GIF, tối đa 8 MB.
- Thư mục `instance/`, môi trường Python và tệp `.env` được loại khỏi Git. Sao lưu dữ liệu SQLite và ảnh riêng nếu cần giữ thông tin.
- Báo cáo CSV, QR và phiếu mượn dạng trang in có thể xem mà không đăng nhập.

## Lưu ý

Thông tin kho, ảnh, tên người mượn, chữ ký dạng tên và phiếu mượn được hiển thị công khai theo cấu hình hiện tại. Không lưu dữ liệu cần giới hạn người xem vào ứng dụng này. Chữ ký hiện là tên nhập, chưa phải chữ ký điện tử vẽ trên màn hình.
