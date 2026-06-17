from fastapi.templating import Jinja2Templates
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _vnd(value):
    try:
        return f"{int(float(value)):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(value)


templates = Jinja2Templates(directory=str(BASE_DIR / "fastapi_templates"))
templates.env.filters["vnd"] = _vnd
