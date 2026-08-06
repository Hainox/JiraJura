FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY alembic.ini .
COPY schema.sql .
COPY import_kml.py .
COPY apply_titul.py .
COPY fix_passwords.py .
COPY bulk_invite.py .
COPY diagnose_logins.py .
COPY titul_2026-08.csv .
COPY alembic/ ./alembic/
RUN mkdir -p /app/uploads

EXPOSE 8000
# --forwarded-allow-ips '*' — без этого uvicorn доверяет X-Forwarded-Proto/Host
# только от 127.0.0.1 (свой дефолт), а nginx подключается по внутренней
# docker-сети со своим IP контейнера; без доверия эти заголовки игнорируются,
# и request.url в pdf_report.py собирается как http://<внутренний хост>:8000
# вместо реального https://.../ :8443 — там на это завязаны ссылки на фото.
# Безопасно: порт api не публикуется наружу (см. docker-compose.prod.yml) —
# достучаться до него может только proxy-контейнер той же сети.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips", "*"]
