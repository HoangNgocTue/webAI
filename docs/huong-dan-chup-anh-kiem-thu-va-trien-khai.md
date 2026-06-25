# Hướng dẫn chụp ảnh cho báo cáo

## 1. Kiểm thử chức năng

Chụp các màn hình sau:

- Trang liên hệ: `http://127.0.0.1:8000/contact/`
  - Ảnh trước khi gửi form.
  - Ảnh sau khi gửi thành công, có mã ticket.
- Trang quản trị ticket: `http://127.0.0.1:8000/quan-tri/tickets/`
  - Ảnh danh sách ticket có ticket vừa tạo.
  - Ảnh chi tiết ticket và phần phản hồi khách hàng.
- Chatbot:
  - Hỏi `laptop`.
  - Hỏi tiếp `dưới 15 tr`.
  - Mở `giỏ hàng`, bấm thêm/xóa sản phẩm.
- Đơn hàng:
  - Giỏ hàng.
  - Checkout.
  - Lịch sử đơn hàng.
  - Hóa đơn.

## 2. Log lỗi

Nếu chạy local:

```powershell
python run_fastapi.py
```

Chụp terminal có các dòng dạng:

```text
INFO: 127.0.0.1:60492 - "POST /contact/ HTTP/1.1" 200 OK
INFO: 127.0.0.1:59997 - "GET /quan-tri/tickets/ HTTP/1.1" 200 OK
ERROR: AI Fallback Error: ...
```

Nếu chạy Docker:

```powershell
docker compose logs -f web
```

## 3. Kiến trúc triển khai

Dùng ảnh có sẵn:

- `docs/kien-truc-trien-khai-ung-dung.svg`
- `docs/kiem-thu-chuc-nang-va-log-loi.svg`

Hai file này có thể chèn trực tiếp vào Word. Nếu Word không nhận SVG, mở file bằng trình duyệt rồi chụp màn hình lại.
