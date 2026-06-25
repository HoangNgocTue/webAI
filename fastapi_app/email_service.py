import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()


def _build_html(subject: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{ margin:0; padding:0; background:#f1f5f9; font-family:'Segoe UI',Arial,sans-serif; }}
  .wrapper {{ max-width:600px; margin:32px auto; background:#ffffff; border-radius:16px;
             box-shadow:0 4px 20px rgba(0,0,0,0.08); overflow:hidden; }}
  .header {{ background:linear-gradient(135deg,#4eaeb9,#2d8fa0); padding:28px 36px; text-align:center; }}
  .header img {{ width:48px; height:48px; }}
  .header h1 {{ color:#ffffff; margin:10px 0 4px; font-size:1.4rem; font-weight:700; letter-spacing:0.5px; }}
  .header p {{ color:rgba(255,255,255,0.85); margin:0; font-size:0.9rem; }}
  .body {{ padding:32px 36px; color:#1e293b; }}
  .body h2 {{ font-size:1.1rem; font-weight:700; margin:0 0 16px; color:#0f172a; }}
  .info-box {{ background:#f8fafc; border-left:4px solid #4eaeb9; border-radius:0 10px 10px 0;
               padding:16px 20px; margin:20px 0; }}
  .info-box .row {{ display:flex; gap:8px; margin-bottom:8px; font-size:0.9rem; }}
  .info-box .row:last-child {{ margin-bottom:0; }}
  .info-box .label {{ color:#64748b; min-width:110px; flex-shrink:0; }}
  .info-box .value {{ color:#0f172a; font-weight:600; }}
  .ticket-badge {{ display:inline-block; background:#ecfdf5; border:1.5px solid #86efac;
                   color:#15803d; padding:8px 20px; border-radius:999px; font-size:1rem;
                   font-weight:700; letter-spacing:1.5px; margin:4px 0 20px; }}
  .desc-box {{ background:#f8fafc; border-radius:10px; padding:16px 20px; font-size:0.9rem;
               color:#374151; line-height:1.6; margin-top:16px; white-space:pre-wrap; }}
  .cta {{ text-align:center; margin:24px 0 8px; }}
  .cta a {{ display:inline-block; background:#4eaeb9; color:#ffffff; padding:12px 32px;
             border-radius:10px; text-decoration:none; font-weight:600; font-size:0.95rem; }}
  .footer {{ background:#f8fafc; padding:20px 36px; text-align:center;
             color:#94a3b8; font-size:0.8rem; border-top:1px solid #e2e8f0; }}
  .footer strong {{ color:#64748b; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>Đà Nẵng Store</h1>
    <p>Cửa hàng công nghệ uy tín tại Đà Nẵng</p>
  </div>
  <div class="body">
    {body_html}
  </div>
  <div class="footer">
    © 2025 <strong>Đà Nẵng Store</strong> &nbsp;|&nbsp; 📞 0905 123 456 &nbsp;|&nbsp; 📍 123 Nguyễn Văn Linh, Đà Nẵng<br>
    Email này được gửi tự động từ hệ thống hỗ trợ kỹ thuật. Vui lòng không reply trực tiếp.
  </div>
</div>
</body>
</html>"""


def send_ticket_confirm(to_email: str, customer_name: str, ticket_id: str,
                        category_label: str, description: str) -> bool:
    """Gửi email xác nhận ticket cho khách hàng."""
    subject = f"[Đà Nẵng Store] Mã ticket hỗ trợ của bạn: {ticket_id}"
    body_html = f"""
    <h2>Xin chào {customer_name}!</h2>
    <p>Chúng tôi đã nhận được yêu cầu hỗ trợ của bạn. Kỹ thuật viên sẽ liên hệ trong <strong>vòng 24 giờ</strong>.</p>
    <p style="margin:8px 0 4px;color:#64748b;font-size:0.88rem;">Mã ticket của bạn:</p>
    <div class="ticket-badge">{ticket_id}</div>
    <div class="info-box">
      <div class="row"><span class="label">Loại vấn đề</span><span class="value">{category_label}</span></div>
    </div>
    <p style="margin:16px 0 6px;font-weight:600;font-size:0.9rem;color:#374151;">Nội dung yêu cầu:</p>
    <div class="desc-box">{description}</div>
    <p style="margin-top:20px;font-size:0.88rem;color:#64748b;">
      Nếu cần thêm thông tin, kỹ thuật viên sẽ liên hệ qua email hoặc số điện thoại bạn cung cấp.
    </p>
    """
    return _send(to_email, subject, body_html)


def send_ticket_admin_notify(admin_email: str, ticket_id: str, customer_name: str,
                             customer_email: str, customer_phone: str,
                             category_label: str, description: str,
                             admin_url: str = "http://localhost:8000/quan-tri/tickets/") -> bool:
    """Gửi email thông báo ticket mới cho admin/kỹ thuật viên."""
    subject = f"[Ticket mới] {ticket_id} — {category_label}"
    phone_str = customer_phone or "<i style='color:#94a3b8'>Không cung cấp</i>"
    body_html = f"""
    <h2>Có ticket hỗ trợ mới!</h2>
    <p>Một khách hàng vừa gửi yêu cầu hỗ trợ. Vui lòng xử lý sớm nhất có thể.</p>
    <div class="info-box">
      <div class="row"><span class="label">Mã ticket</span><span class="value">{ticket_id}</span></div>
      <div class="row"><span class="label">Họ tên</span><span class="value">{customer_name}</span></div>
      <div class="row"><span class="label">Email</span><span class="value">{customer_email}</span></div>
      <div class="row"><span class="label">SĐT</span><span class="value">{phone_str}</span></div>
      <div class="row"><span class="label">Loại vấn đề</span><span class="value">{category_label}</span></div>
    </div>
    <p style="margin:16px 0 6px;font-weight:600;font-size:0.9rem;color:#374151;">Nội dung:</p>
    <div class="desc-box">{description}</div>
    <div class="cta">
      <a href="{admin_url}">Xem & Xử lý tại Admin Panel</a>
    </div>
    """
    return _send(admin_email, subject, body_html)


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Gửi email plain text (dùng cho trường hợp chung)."""
    host_user = os.getenv("EMAIL_HOST_USER", "")
    host_pass = os.getenv("EMAIL_HOST_PASSWORD", "")
    if not host_user or not host_pass:
        print("[Email] Credentials not configured.")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = f"Đà Nẵng Store <{host_user}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(host_user, host_pass)
            server.sendmail(host_user, to_email, msg.as_string())
        print(f"[Email] Sent to {to_email}")
        return True
    except Exception as e:
        print(f"[Email] Error: {e}")
        return False


def _send(to_email: str, subject: str, body_html: str) -> bool:
    """Internal: gửi email HTML qua Gmail SMTP."""
    host_user = os.getenv("EMAIL_HOST_USER", "")
    host_pass = os.getenv("EMAIL_HOST_PASSWORD", "")
    if not host_user or not host_pass:
        print("[Email] Credentials not configured — set EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in .env")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"Kỹ thuật viên Đà Nẵng Store <{host_user}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        # Plain text fallback
        plain = subject
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(_build_html(subject, body_html), "html", "utf-8"))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(host_user, host_pass)
            server.sendmail(host_user, to_email, msg.as_string())
        print(f"[Email] HTML email sent to {to_email} | subject: {subject}")
        return True
    except Exception as e:
        print(f"[Email] Error sending to {to_email}: {e}")
        return False
