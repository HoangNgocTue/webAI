# Đà Nẵng Store – Web Bán Hàng Tích Hợp AI Chatbot

Website thương mại điện tử bán đồ công nghệ, tích hợp AI Chatbot (Claude AI) hỗ trợ khách hàng và hệ thống quản lý ticket tự động. Xây dựng bằng **FastAPI** + **SQLAlchemy** + **PostgreSQL**.

---

## Tính năng chính

- Mua sắm sản phẩm công nghệ (laptop, điện thoại, linh kiện)
- Chatbot AI (Claude Sonnet) tư vấn sản phẩm và hỗ trợ khách hàng
- Tự động phân loại lỗi và tạo ticket hỗ trợ
- Khách hàng nhận email thông báo khi ticket được xử lý
- Quản lý đơn hàng, giỏ hàng, thanh toán, hóa đơn
- Trang quản trị riêng tại `/quan-tri` cho dashboard, đơn hàng, sản phẩm, người dùng, danh mục, hóa đơn và support ticket

---

## Yêu cầu hệ thống

| Cách chạy | Yêu cầu |
|---|---|
| Local (SQLite) | Python 3.11+ |
| Docker (PostgreSQL) | Docker Desktop |

---

## Cách 1 — Chạy Local (SQLite)

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
pip install -r requirements_fastapi.txt
```

### 4. Tạo file `.env`

```bash
cp .env.example .env
```

Mở `.env` và điền vào:

```env
# Bắt buộc cho chatbot
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Bắt buộc để gửi email thông báo ticket
EMAIL_HOST_USER=your_gmail@gmail.com
EMAIL_HOST_PASSWORD=your_gmail_app_password

# Tuỳ chọn (để trống = dùng SQLite mặc định)
DATABASE_URL=
SECRET_KEY=change-me-in-production
```

> **Lấy API key Claude:** Đăng ký tại [platform.claude.com](https://platform.claude.com) → API Keys → Create Key
>
> **Gmail App Password:** Vào [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → tạo mật khẩu ứng dụng (cần bật Xác minh 2 bước trước)

### 5. Chạy server

```bash
python run_fastapi.py
```

Truy cập: [http://127.0.0.1:8000](http://127.0.0.1:8000)

Quản trị: [http://127.0.0.1:8000/quan-tri](http://127.0.0.1:8000/quan-tri)

---

## Cách 2 — Chạy bằng Docker (PostgreSQL)

### 1. Clone project & tạo file `.env`

```bash
git clone https://github.com/HoangNgocTue/webAI.git
cd webAI
cp .env.example .env
```

Điền các biến bắt buộc vào `.env` (xem hướng dẫn ở Cách 1 bước 4).

### 2. Build và chạy

```bash
docker compose up --build
```

App tự động:
- Khởi động PostgreSQL
- Build image FastAPI
- Chạy server tại [http://localhost:8000](http://localhost:8000)

### 3. Migrate dữ liệu từ SQLite sang PostgreSQL (chạy 1 lần)

Nếu bạn có dữ liệu cũ trong `db.sqlite3` và muốn chuyển sang PostgreSQL:

```bash
# Đặt DATABASE_URL trỏ tới PostgreSQL đang chạy trong Docker
# Windows PowerShell:
$env:DATABASE_URL = "postgresql://danang_user:danang_pass_2024@localhost:5432/danang_store"

# macOS/Linux:
export DATABASE_URL=postgresql://danang_user:danang_pass_2024@localhost:5432/danang_store

python migrate_to_postgres.py
```

### 4. Dừng Docker

```bash
docker compose down          # dừng nhưng giữ dữ liệu
docker compose down -v       # dừng và xóa toàn bộ dữ liệu
```

---

## Cấu trúc thư mục

```
webAI/
├── fastapi_app/            # Ứng dụng FastAPI chính
│   ├── main.py             # Entry point, middleware, mount routes
│   ├── database.py         # SQLAlchemy engine (SQLite / PostgreSQL)
│   ├── models.py           # ORM models (User, Product, Order...)
│   ├── auth.py             # Xác thực PBKDF2 (tương thích Django)
│   ├── dependencies.py     # BaseContext (user, categories, cart)
│   ├── admin_setup.py      # Legacy SQLAdmin setup (không mount mặc định)
│   ├── email_service.py    # Gửi email Gmail SMTP
│   ├── chatbot_service.py  # Logic chatbot Claude AI
│   └── routers/            # Các router theo tính năng
│       ├── shop.py         # Trang chủ, chi tiết, danh mục, tìm kiếm
│       ├── auth_router.py  # Đăng nhập, đăng ký, đăng xuất
│       ├── cart_router.py  # Giỏ hàng
│       ├── orders_router.py# Checkout, hóa đơn, lịch sử đơn hàng
│       ├── profile_router.py # Trang cá nhân
│       ├── pages_router.py # Giới thiệu, liên hệ
│       └── chatbot_router.py # Chatbot API
├── fastapi_templates/      # Templates Jinja2
├── static/                 # CSS, JS, hình ảnh tĩnh
│   ├── app/css/
│   ├── app/js/
│   └── images/             # Ảnh sản phẩm
├── Dockerfile
├── docker-compose.yml
├── requirements_fastapi.txt
├── run_fastapi.py          # Chạy local
├── init_db.py              # Tạo bảng mới (fresh deploy)
├── migrate_to_postgres.py  # Chuyển dữ liệu SQLite → PostgreSQL
├── db.sqlite3              # Database SQLite (local)
└── .env                    # API keys (không commit)
```

---

## Biến môi trường

| Biến | Bắt buộc | Mô tả |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | API key từ platform.claude.com |
| `EMAIL_HOST_USER` | ✅ | Gmail dùng để gửi thông báo |
| `EMAIL_HOST_PASSWORD` | ✅ | App Password của Gmail |
| `SECRET_KEY` | ✅ (prod) | Khóa bí mật cho session cookie |
| `DATABASE_URL` | ❌ | PostgreSQL URL — để trống thì dùng SQLite |
| `POSTGRES_PASSWORD` | ❌ | Mật khẩu PostgreSQL cho Docker Compose |
| `ADMIN_SECRET_KEY` | ❌ | Khóa riêng cho trang admin |

---

## Sử dụng Chatbot

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

---

## Trang quản trị

Truy cập: [http://127.0.0.1:8000/quan-tri](http://127.0.0.1:8000/quan-tri)

Đăng nhập bằng tài khoản có quyền `is_staff = True`.

- Quản lý sản phẩm, danh mục, đơn hàng, khách hàng, hóa đơn
- Xem và xử lý ticket hỗ trợ
- Khi đổi trạng thái ticket → hệ thống tự gửi email cho khách

**Trạng thái ticket:**
| Trạng thái | Ý nghĩa |
|---|---|
| `open` | Ticket mới tạo, chờ xử lý |
| `in_progress` | Nhân viên đang xem |
| `resolved` | Hoàn thành, email gửi cho khách |

---

## Thông tin cửa hàng

- **Tên:** Đà Nẵng Store
- **Hotline:** 0905 123 456
- **Địa chỉ:** 123 Nguyễn Văn Linh, Đà Nẵng
- **Chính sách:** Bảo hành 12 tháng | Đổi trả 7 ngày | Miễn phí ship đơn trên 1 triệu
