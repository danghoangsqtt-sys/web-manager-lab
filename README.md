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

## Chạy sau reverse proxy / máy chủ production

Cài các gói trong `requirements.txt`, đặt `FLASK_SECRET_KEY`, `ADMIN_USERNAME` và một `ADMIN_PASSWORD` riêng, rồi chạy `gunicorn --bind 0.0.0.0:$PORT app:app`. Cần dùng ổ đĩa bền vững cho `LAB_DATABASE` và `LAB_UPLOADS`; không dùng filesystem tạm thời cho dữ liệu thật. Trước khi mở công khai, cấu hình sao lưu và nơi lưu ảnh riêng phù hợp.

## Dữ liệu

- SQLite mặc định lưu ở `instance/lab.sqlite3`.
- Ảnh gốc lưu riêng trên máy chủ tại `instance/uploads/`; trang web chỉ gửi bản PNG đã đóng dấu tên tác giả `Lê Bá Đăng Hoàng`. Hỗ trợ PNG, JPG, WEBP và GIF, tối đa 8 MB.
- Thư mục `instance/`, môi trường Python và tệp `.env` được loại khỏi Git. Sao lưu dữ liệu SQLite và ảnh riêng nếu cần giữ thông tin.
- QR và phiếu mượn có thể xem mà không đăng nhập; khách xem phiếu chỉ thấy trạng thái “Đã ký”, không thấy tên chữ ký. Báo cáo CSV chứa chữ ký chỉ admin được tải.

## Lưu ý

Thông tin kho, ảnh đã đóng dấu, tên người mượn và phiếu mượn được hiển thị công khai theo cấu hình hiện tại. Website hạn chế menu chuột phải, kéo ảnh và sao chép nội dung phiếu trong trình duyệt, nhưng không thể ngăn chụp màn hình, dùng thiết bị khác chụp lại, mở công cụ lập trình hoặc lấy nội dung công khai. Watermark giúp nhận diện nguồn, không phải cơ chế bảo mật. Không đưa ảnh/chữ ký nhạy cảm lên website công khai; muốn bảo vệ thực sự cần giới hạn quyền truy cập và không cung cấp ảnh gốc cho người xem. Chữ ký hiện là tên nhập, chưa phải chữ ký điện tử vẽ trên màn hình.
