# ======= BEGIN Dockerfile =======
# Multi-stage image to run both the crawler and FastAPI service
FROM python:3.11-slim AS base
WORKDIR /app

# ---- System libraries required by trafilatura (lxml, brotli, etc.) ----
RUN apt-get update && apt-get install -y \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# ---- Python dependencies ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Application code ----
COPY nil_wire.py .

# (optional) copy a default config.yaml if you want to bake it in
# COPY config.yaml .

# ---- Runtime environment variables ----
ENV PYTHONUNBUFFERED=1 \
    UVCORN_HOST="0.0.0.0" \
    UVCORN_PORT="8000" \
    CRAWL_INTERVAL_MIN="5"

# dumb-init = simple PID 1 so both processes shut down cleanly
RUN pip install --no-cache-dir dumb-init

# ---- Start both processes:
#      • background crawler (interval set by $CRAWL_INTERVAL_MIN)
#      • uvicorn API on $UVCORN_PORT
CMD dumb-init bash -c "
    python nil_wire.py crawl --interval $CRAWL_INTERVAL_MIN &
    python nil_wire.py serve --host $UVCORN_HOST --port $UVCORN_PORT
"
# ======== END Dockerfile ========
