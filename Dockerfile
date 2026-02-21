# Convert God - Docker image for Render (web + worker)
FROM python:3.13-slim

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

# Collectstatic during build is handled by Render build command; keep image generic.

# Default command (Render overrides per service)
CMD ["gunicorn", "convert_god.wsgi:application", "--bind", "0.0.0.0:10000"]
