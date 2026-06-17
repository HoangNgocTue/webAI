import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()


def send_email(to_email: str, subject: str, body: str) -> bool:
    host_user = os.getenv("EMAIL_HOST_USER", "")
    host_pass = os.getenv("EMAIL_HOST_PASSWORD", "")
    if not host_user or not host_pass:
        print("[Email] Credentials not configured.")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = host_user
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
