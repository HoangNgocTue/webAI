import hashlib
import base64
import secrets


def check_django_password(password: str, encoded: str) -> bool:
    """Verify Django PBKDF2 SHA-256 password — compatible with Django 4.x / 5.x"""
    try:
        parts = encoded.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        _, iterations, salt, hash_val = parts
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )
        return base64.b64encode(dk).decode("ascii") == hash_val
    except Exception:
        return False


def make_django_password(password: str) -> str:
    """Create a Django-compatible PBKDF2 password hash (Django 5.x default: 870000 iterations)"""
    iterations = 870000
    salt = secrets.token_urlsafe(12)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    hash_val = base64.b64encode(dk).decode("ascii")
    return f"pbkdf2_sha256${iterations}${salt}${hash_val}"
