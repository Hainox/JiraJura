#!/usr/bin/env sh
set -e

# БД может быть ещё не готова принимать соединения сразу после старта её
# контейнера (в dev-compose у depends_on нет condition: service_healthy) —
# несколько попыток с паузой вместо мгновенного падения контейнера api.
i=0
until alembic upgrade head; do
  i=$((i + 1))
  if [ "$i" -ge 10 ]; then
    echo "alembic upgrade head: не удалось после $i попыток" >&2
    exit 1
  fi
  echo "БД ещё не готова, повтор через 3с ($i/10)..." >&2
  sleep 3
done

# --forwarded-allow-ips '*' — без этого uvicorn доверяет X-Forwarded-Proto/Host
# только от 127.0.0.1 (свой дефолт), а nginx подключается по внутренней
# docker-сети со своим IP контейнера; без доверия эти заголовки игнорируются,
# и request.url в pdf_report.py собирается как http://<внутренний хост>:8000
# вместо реального https://.../ :8443 — там на это завязаны ссылки на фото.
# Безопасно: порт api не публикуется наружу в проде (см. docker-compose.prod.yml) —
# достучаться до него может только proxy-контейнер той же сети.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --forwarded-allow-ips '*'
