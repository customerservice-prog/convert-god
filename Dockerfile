# Convert God - Docker image for Render (web + worker)
# Playwright base includes Chromium + dependencies for headless browser mode.
FROM mcr.microsoft.com/playwright/python:v1.50.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ffmpeg for transcoding
RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

RUN chmod +x /app/entrypoint.sh

# One image: choose role via SERVICE_ROLE=web|worker
ENTRYPOINT ["/app/entrypoint.sh"]
