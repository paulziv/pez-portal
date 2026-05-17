FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Railway injects PORT at runtime; default to 8080 for local testing
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
