FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements_fastapi.txt .
RUN pip install --no-cache-dir -r requirements_fastapi.txt

# Copy application code
COPY fastapi_app/ ./fastapi_app/
COPY fastapi_templates/ ./fastapi_templates/
COPY static/ ./static/
COPY .env* ./

# Create directory for SQLite (used when DATABASE_URL is not set)
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "fastapi_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
