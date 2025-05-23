# ======= BEGIN Dockerfile =======
# Docker image that runs BOTH the NIL-News crawler and FastAPI API
FROM python:3.11-slim AS base
WORKDIR /app

# — System libraries required by trafilatura —
RUN apt-get update && apt-get install -y \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# — Python dependencies —
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# — Application code —
COPY nil_news.py .

# — Environment variables —
ENV PYTHONUNBUFFERED=1 \
    UVCORN_HOST=0.0.0.0 \
    UVCORN_PORT=8000 \
    CRAWL_INTERVAL_MIN=5

# Small PID-1 helper so both processes exit cleanly
RUN pip install --no-cache-dir dumb-init

# — Start background crawler + API (single-line CMD avoids parse errors) —
CMD ["bash", "-c", "python nil_news.py crawl --interval ${CRAWL_INTERVAL_MIN} & python nil_news.py serve --host ${UVCORN_HOST} --port ${UVCORN_PORT}"]
# ======== END Dockerfile ========
