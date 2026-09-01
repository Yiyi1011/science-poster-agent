FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PORT=9000 \
    SCIENCE_POSTER_DATA_DIR=/data

WORKDIR /app
COPY backend/ /app/backend/
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "/app/backend[video]" \
    && useradd --create-home --uid 10001 scivis \
    && mkdir -p /data \
    && chown -R scivis:scivis /data
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist

WORKDIR /app/backend
USER scivis
EXPOSE 9000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').getenv('PORT','9000') + '/api/health', timeout=3)" || exit 1
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9000}"]
