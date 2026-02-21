web: gunicorn convert_god.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --threads 8 --worker-class gthread --timeout 90 --log-level info --access-logfile - --error-logfile -
worker: python manage.py worker
