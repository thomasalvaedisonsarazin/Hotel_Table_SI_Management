FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app ./app
COPY alembic.ini .
COPY ./alembic ./alembic

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# One worker on purpose: the live-update hub and engine loop run inside the process.
# Trusting forwarded addresses is safe only because this port is reachable just through nginx.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
