"""
Đà Nẵng Store — FastAPI Entry Point
Run locally: python run_fastapi.py
Docker:      docker compose up --build
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "fastapi_app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=["fastapi_app", "fastapi_templates"],
    )
