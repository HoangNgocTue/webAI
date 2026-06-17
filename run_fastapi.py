"""
Đà Nẵng Store — FastAPI Entry Point
Run: python run_fastapi.py
Or:  uvicorn fastapi_app.main:app --reload
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "fastapi_app.main:app",
        host="127.0.0.1",
        port=8001,  # Port 8001 để chạy song song với Django (port 8000)
        reload=True,
        reload_dirs=["fastapi_app", "fastapi_templates"],
    )
