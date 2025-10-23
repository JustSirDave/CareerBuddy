FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (keep minimal; gcc only if needed later)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Install Python deps (add more as you need them)
RUN pip install --upgrade pip && \
    pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" httpx redis loguru \
               "pydantic>=2.0" "SQLAlchemy>=2.0" "psycopg[binary]>=3.1"

# With build context = ./backend, the app folder is right here
COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
