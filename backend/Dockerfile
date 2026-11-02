# Backend API: Flask app served by gunicorn. Migrations run on start, before the server.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FLASK_APP=wsgi \
    UPLOAD_DIR=/data/uploads

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt "gunicorn>=26,<27"
COPY . .

# Run as an unprivileged user; uploaded receipts live in a volume at /data/uploads.
RUN useradd --create-home --uid 10001 app && mkdir -p /data/uploads && chown -R app /data
USER app

EXPOSE 5000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=4)"

# One process: login rate limits are counted in memory per process (see docs/deployment.md).
# Threads let slow assistant questions run while other requests are served.
# No access log here: some API paths carry invitation tokens.
CMD ["sh", "-c", "flask db upgrade && exec gunicorn --workers 1 --threads 8 --timeout 300 --bind 0.0.0.0:5000 --forwarded-allow-ips='*' wsgi:app"]
