FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright PORT=7860

# libatomic1 for Playwright's driver; Noto fonts so screenshots of Arabic, Urdu, Malayalam... pages render real glyphs
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 fonts-noto-core && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && playwright install --with-deps chromium

COPY . .
RUN useradd -m -u 1000 rasid && chown -R rasid /app
USER rasid

EXPOSE 7860
CMD uvicorn rasid.api:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips="*"
