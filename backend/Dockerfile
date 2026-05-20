FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install curl and LibreOffice core deps first (pulls all shared libraries).
# Split into two RUN commands so each step stays within the apt archive cache
# size limit on constrained build environments (Railway).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        libreoffice-core \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Install LibreOffice Writer last — shared deps are already present, so
# this step only fetches the small writer-specific packages.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Copy pyproject.toml and install dependencies
COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --only main --no-interaction --no-ansi --no-root

# With build context = ./backend, the app folder is right here
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
