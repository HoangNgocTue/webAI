# Đà Nẵng Store – Web Bán Hàng Tích Hợp AI Chatbot

Website thương mại điện tử bán đồ công nghệ, tích hợp AI Chatbot (Claude AI) hỗ trợ khách hàng và hệ thống quản lý ticket tự động.

---

## Tính năng chính

- Mua sắm sản phẩm công nghệ (laptop, điện thoại, linh kiện)
- Chatbot AI (Claude Sonnet) tư vấn sản phẩm và hỗ trợ khách hàng
- Tự động phân loại lỗi và tạo ticket hỗ trợ
- Khách hàng nhận email thông báo khi ticket được xử lý
- Quản lý đơn hàng, giỏ hàng, thanh toán
- Trang quản trị (Django Admin)

---

## Yêu cầu hệ thống

- Python 3.10+
- pip

---

## Cài đặt

### 1. Clone project

```bash
git clone https://github.com/HoangNgocTue/webAI.git
cd webAI
```

### 2. Tạo môi trường ảo

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Cài thư viện

```bash
pip install django python-dotenv anthropic pymysql
```

### 4. Tạo file `.env`

Tạo file `.env` ở thư mục gốc với nội dung:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Email Gmail để gửi thông báo ticket
EMAIL_HOST_USER=your_gmail@gmail.com
EMAIL_HOST_PASSWORD=your_gmail_app_password

# Tùy chọn: thay đổi model Claude (mặc định: claude-sonnet-4-6)
# CLAUDE_MODEL=claude-sonnet-4-6
```

> **Lấy API key Claude:** Đăng ký tại [platform.claude.com](https://platform.claude.com) → API Keys → Create Key
>
> **Gmail App Password:** Vào [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → tạo mật khẩu ứng dụng (cần bật Xác minh 2 bước trước)

### 5. Migrate database

```bash
python manage.py migrate
```

### 6. Tạo tài khoản admin

```bash
python manage.py createsuperuser
```

### 7. Chạy server

```bash
python manage.py runserver
```

Truy cập: [http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## Sử dụng

### Chatbot AI

Nhấn icon chat ở góc dưới phải trang web để mở chatbot.

**Tư vấn sản phẩm:**
```
"Tìm laptop dưới 15 triệu"
"Điện thoại tầm 8 triệu"
"MacBook có không?"
```

**Báo lỗi / Yêu cầu hỗ trợ:**
```
"Tôi không đặt hàng được"
"Không đăng nhập được tài khoản"
"Thanh toán bị lỗi"
```
→ Bot tự động tạo mã ticket `TKT-XXXXXX` và hỏi email để nhận thông báo.

**Kiểm tra trạng thái ticket:**
```
"TKT-ABC123"
"kiểm tra ticket TKT-ABC123"
```

### Trang quản trị

Truy cập: [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)

- Quản lý sản phẩm, đơn hàng, khách hàng
- Xem và xử lý ticket hỗ trợ
- Khi đổi trạng thái ticket → hệ thống tự gửi email cho khách

**Trạng thái ticket:**
| Trạng thái | Ý nghĩa |
|---|---|
| Chờ xử lý | Ticket mới tạo |
| Đang xử lý | Nhân viên đang xem |
| Đã giải quyết | Hoàn thành, email gửi cho khách |

---

## Cấu trúc thư mục

```
webAI/
├── app/                    # App chính (sản phẩm, đơn hàng)
│   ├── models.py           # Product, Order, Cart...
│   ├── views.py
│   └── templates/
├── chatbot/                # App chatbot AI
│   ├── claude_client.py    # Kết nối Anthropic API
│   ├── models.py           # SupportTicket
│   ├── signals.py          # Gửi email tự động
│   ├── views.py            # Logic chatbot
│   └── templates/
├── webbanhang/             # Cấu hình Django
│   └── settings.py
├── .env                    # API keys (không commit)
├── .gitignore
└── manage.py
```

---

## Biến môi trường

| Biến | Bắt buộc | Mô tả |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | API key từ platform.claude.com |
| `EMAIL_HOST_USER` | ✅ | Gmail dùng để gửi thông báo |
| `EMAIL_HOST_PASSWORD` | ✅ | App Password của Gmail |
| `CLAUDE_MODEL` | ❌ | Model Claude (mặc định: `claude-sonnet-4-6`) |

---

## Thông tin cửa hàng

- **Tên:** Đà Nẵng Store
- **Hotline:** 0905 123 456
- **Địa chỉ:** 123 Nguyễn Văn Linh, Đà Nẵng
- **Chính sách:** Bảo hành 12 tháng | Đổi trả 7 ngày | Miễn phí ship đơn trên 1 triệu
