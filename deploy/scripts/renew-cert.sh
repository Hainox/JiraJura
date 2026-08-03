#!/usr/bin/env bash
# Продление сертификата — вызывается из cron (root crontab), см. deploy/README.md.
# Та же логика, что и issue-cert.sh: секундная остановка чужого nginx-контейнера
# бота на время HTTP-01 челленджа, никакие файлы бота не трогаются.
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ ! -f .env ]; then
  echo "Нет .env в корне репозитория." >&2
  exit 1
fi
set -a; source .env; set +a
: "${BOT_COMPOSE_PROJECT:=yuvibotv2}"
: "${BOT_NGINX_SERVICE:=nginx-https}"

echo "$(date -Is) ==> renew-cert.sh: останавливаю $BOT_NGINX_SERVICE..."
docker compose -p "$BOT_COMPOSE_PROJECT" stop "$BOT_NGINX_SERVICE"

cleanup() {
  echo "$(date -Is) ==> renew-cert.sh: поднимаю $BOT_NGINX_SERVICE обратно..."
  docker compose -p "$BOT_COMPOSE_PROJECT" start "$BOT_NGINX_SERVICE"
}
trap cleanup EXIT

docker run --rm \
  -p 80:80 \
  -v "$(pwd)/deploy/certbot/conf:/etc/letsencrypt" \
  certbot/certbot renew --quiet --standalone

docker compose -f docker-compose.prod.yml exec proxy nginx -s reload 2>/dev/null || true

echo "$(date -Is) ==> renew-cert.sh: готово."
