FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install build-essential and curl first (smaller download), then clean cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy pyproject.toml and install dependencies (needs build-essential for C extensions)
COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi --no-root

# Remove build-essential after Python deps are compiled to free disk space
RUN apt-get purge -y --auto-remove build-essential && rm -rf /var/lib/apt/lists/*

# Install LibreOffice for PDF conversion (large package, needs its own layer)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    libreoffice-core \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# With build context = ./backend, the app folder is right here
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
