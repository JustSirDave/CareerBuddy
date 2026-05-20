FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install LibreOffice for DOCX→PDF conversion.
# Dir::Cache::archives redirects package downloads to /tmp which has more
# headroom than /var/cache/apt/archives/ in constrained build environments.
RUN mkdir -p /tmp/apt-archives \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        -o Dir::Cache::archives=/tmp/apt-archives \
        curl \
        libreoffice-writer \
        libreoffice-core \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/apt-archives

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
