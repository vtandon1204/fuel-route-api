FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/var/cache

EXPOSE 8000

# Migrate, load the bundled fuel price data (idempotent-ish: pass --clear
# if you re-run this against a stale volume), then serve.
CMD ["sh", "-c", "python manage.py migrate --noinput && \
                   (python manage.py shell -c 'from routing.models import FuelStation; import sys; sys.exit(0 if FuelStation.objects.exists() else 1)' || python manage.py load_fuel_prices) && \
                   python manage.py runserver 0.0.0.0:8000"]
