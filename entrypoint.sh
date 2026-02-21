#!/usr/bin/env sh
set -eu

ROLE="${SERVICE_ROLE:-web}"

# Always run migrations + collectstatic on boot for simplicity.
# (Render disks are ephemeral except Postgres; this is safe and fast for small apps.)
python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ "$ROLE" = "worker" ]; then
  exec python manage.py worker
fi

# default: web
exec gunicorn convert_god.wsgi:application \
  --bind 0.0.0.0:${PORT:-10000} \
  --workers ${WEB_WORKERS:-2} \
  --threads ${WEB_THREADS:-8} \
  --worker-class gthread \
  --timeout ${WEB_TIMEOUT:-90} \
  --access-logfile - \
  --error-logfile -
