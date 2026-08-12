#!/usr/bin/env bash
# Продление сертификата на ВЫДЕЛЕННОМ сервере (не делит хост с ботом) —
# вызывается из cron (root crontab), см. deploy/README.md. Аналог
# renew-cert.sh, но без секундной остановки чужого nginx-контейнера: тут
# порт 80 весь наш, продление идёт через webroot, пока proxy как обычно
# работает (см. комментарий в issue-cert-standalone.sh).
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ ! -f .env ]; then
  echo "Нет .env в корне репозитория." >&2
  exit 1
fi
set -a; source .env; set +a

echo "$(date -Is) ==> renew-cert-standalone.sh: продлеваю (webroot, без остановки proxy)..."
docker compose -f docker-compose.prod.yml run --rm \
  --entrypoint certbot certbot renew --quiet --webroot -w /var/www/certbot

docker compose -f docker-compose.prod.yml exec proxy nginx -s reload 2>/dev/null || true

echo "$(date -Is) ==> renew-cert-standalone.sh: готово."
