# Pinned minor so rebuilds are reproducible; bump deliberately.
FROM python:3.11.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health', timeout=3)"

# --workers 1 is load-bearing: app.py holds module-level singletons (one
# controller, arbiter, binder, leash, power tracker) and the BiBoard firmware
# caps WebSocket clients at 2 — a second worker would be a second robot
# client with its own conflicting state. Scale threads, never workers.
# The container runs as root on purpose: the /data volume was created
# root-owned by earlier images and gunicorn must keep writing bittle.db there.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "app.app:app"]
