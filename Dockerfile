FROM python:3.11-slim

WORKDIR /app

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY webapp.py backup_core.py ./

ENV PORT=8000
EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "600", "webapp:app"]
