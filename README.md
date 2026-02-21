# Convert God

Private video converter (MP4 H.264 + AAC) with presigned uploads + background worker.

## Features

- Upload via presigned URL (R2/S3 compatible)
- Create conversion jobs with presets: original/1080p/720p/480p
- Worker runs ffmpeg and uploads output
- UI is a single page (HTML/JS) served by Django
- Basic Auth (private)
- Signed download links (expires)
- Auto-delete job artifacts (management command)

## Local dev

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Worker:

```bash
python manage.py worker
```

## Deploy

- Web service: gunicorn
- Worker service: `python manage.py worker`
- Storage: Cloudflare R2
- DB: Postgres

