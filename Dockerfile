# --- Base ---
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    tesseract-ocr \
    poppler-utils \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*



# --- Dependencies ---
FROM base AS deps
COPY requirements.txt .
RUN pip install -r requirements.txt

# --- Runtime ---
FROM deps AS runtime
COPY . .

RUN mkdir -p data/uploads logs && \
    addgroup --system app && adduser --system --ingroup app app && \
    chown -R app:app /app

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

USER root

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
