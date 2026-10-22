# Website quản lý Phòng thí nghiệm Điện tử số

Ứng dụng Flask có giao diện gọn theo phong cách Notion. Khách xem kho, ảnh thiết bị, mã QR, số liệu và phiếu mượn mà không cần đăng nhập. Chỉ admin mới được thêm mặt hàng, tải ảnh, lập phiếu, xác nhận trả và tải báo cáo CSV.

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

Cài các gói trong `requirements.txt`, đặt `FLASK_SECRET_KEY`, `ADMIN_USERNAME` và một `ADMIN_PASSWORD` riêng, rồi chạy `gunicorn --bind 0.0.0.0:$PORT app:app`. Với máy chủ có ổ đĩa bền vững, ứng dụng có thể dùng `LAB_DATABASE` và `LAB_UPLOADS` cục bộ. Không dùng hai thư mục này trên môi trường serverless.

## Triển khai miễn phí thử nghiệm: Vercel + Supabase

Mô hình này dùng Vercel cho ứng dụng Flask và một dự án Supabase cho cả PostgreSQL lẫn Supabase Storage. Ảnh gốc nằm trong bucket `lab-files` ở chế độ private; trang chỉ trả về ảnh đã đóng dấu qua ứng dụng.

1. Tạo một project Supabase, đặt mật khẩu cơ sở dữ liệu mạnh và chờ project hoạt động.
2. Mở **SQL Editor → New query**, sao chép toàn bộ nội dung `supabase_setup.sql`, dán vào và chọn **Run**. Lệnh này tạo bảng `users`, `items`, `loans`, các index và bucket private `lab-files` chỉ nhận ảnh tối đa 4 MB.
3. Mở **Connect**, chọn **Shared pooler / Transaction mode**, sao chép chuỗi kết nối và thêm `?sslmode=require` nếu chuỗi chưa có tham số này. Dùng chuỗi này cho `DATABASE_URL`.
4. Mở **Project Settings → API** để lấy `SUPABASE_URL` và service-role key. Chỉ dùng service-role key trong Vercel; không đưa khóa này vào trình duyệt, GitHub hoặc tệp `.env` đã công khai.
5. Trên Vercel, nhập repository GitHub `danghoangsqtt-sys/web-manager-lab`. Vercel tự nhận diện Flask/Python. Trong **Settings → Environment Variables**, đặt:
   - `DATABASE_URL`: chuỗi Shared pooler của Supabase.
   - `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET=lab-files`.
   - `FLASK_SECRET_KEY`: một chuỗi ngẫu nhiên dài, cố định.
   - `ADMIN_USERNAME` và `ADMIN_PASSWORD`: thông tin admin mới, không dùng mật khẩu mẫu.
6. Chọn **Deploy**. Ở lần truy cập đầu, ứng dụng tự tạo admin nếu chưa có. Đăng nhập `/login`, sau đó thêm thiết bị và ảnh. Dữ liệu cục bộ cũ không tự được đưa lên; với cơ sở dữ liệu sạch hiện tại chỉ cần thêm dữ liệu thật trên website.

Vercel giới hạn toàn bộ request/response của Function ở 4,5 MB, nên biểu mẫu và bucket đều giới hạn ảnh ở 4 MB. Muốn lưu ảnh lớn hơn cần bổ sung luồng tải trực tiếp lên Supabase Storage.

## Dữ liệu

- Khi không đặt `DATABASE_URL`, SQLite mặc định lưu ở `instance/lab.sqlite3`. Khi đặt `DATABASE_URL`, ứng dụng dùng PostgreSQL; đây là chế độ cần dùng trên Vercel.
- Khi không đặt thông tin Supabase Storage, ảnh gốc lưu ở `instance/uploads/`. Khi đặt `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` và `SUPABASE_STORAGE_BUCKET`, ảnh gốc lưu trong bucket Supabase private; trang web chỉ gửi bản ảnh đã đóng dấu tên tác giả `Lê Bá Đăng Hoàng`. Hỗ trợ PNG, JPG, WEBP và GIF, tối đa 4 MB.
- Kho được chia theo nhóm tài sản: máy tính, KIT thực hành, board mạch & module, linh kiện điện tử, thiết bị đo, dụng cụ & phụ kiện và nhóm khác. Giá đơn vị là tùy chọn, nhập bằng VNĐ để tính giá trị tồn kho.
- Báo cáo CSV dùng định dạng phù hợp với Excel, có tiêu đề, ngày xuất, nhóm tài sản, giá trị ước tính, tình trạng mượn/trả và phần tổng hợp cuối báo cáo.
- Thư mục `instance/`, môi trường Python và tệp `.env` được loại khỏi Git. Sao lưu dữ liệu SQLite và ảnh riêng nếu cần giữ thông tin. Với Supabase, xuất dữ liệu PostgreSQL và sao lưu Storage định kỳ; lưu riêng các khóa truy cập.
- QR và phiếu mượn có thể xem mà không đăng nhập; khách xem phiếu chỉ thấy trạng thái “Đã ký”, không thấy tên chữ ký. Báo cáo CSV chứa chữ ký chỉ admin được tải.

## Lưu ý

Thông tin kho, ảnh đã đóng dấu, tên người mượn và phiếu mượn được hiển thị công khai theo cấu hình hiện tại. Website hạn chế menu chuột phải, kéo ảnh và sao chép nội dung phiếu trong trình duyệt, nhưng không thể ngăn chụp màn hình, dùng thiết bị khác chụp lại, mở công cụ lập trình hoặc lấy nội dung công khai. Watermark giúp nhận diện nguồn, không phải cơ chế bảo mật. Không đưa ảnh/chữ ký nhạy cảm lên website công khai; muốn bảo vệ thực sự cần giới hạn quyền truy cập và không cung cấp ảnh gốc cho người xem. Chữ ký hiện là tên nhập, chưa phải chữ ký điện tử vẽ trên màn hình.
