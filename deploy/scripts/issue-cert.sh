#!/usr/bin/env bash
# Первичный выпуск сертификата Let's Encrypt для JiraJura на этом сервере.
#
# Порт 80 (обязателен для HTTP-01 челленджа Let's Encrypt — не настраивается)
# постоянно занят чужим nginx-контейнером бота (yuvibotv2-nginx-https-1).
# Поэтому на несколько секунд: (1) останавливаем контейнер бота командой
# `docker compose stop` — файлы бота не трогаем вообще, (2) сертификат
# получает временный standalone-certbot, который сам ненадолго слушает
# порт 80, (3) сразу поднимаем контейнер бота обратно.
#
# Запускать из корня репозитория JiraJura на сервере: ./deploy/scripts/issue-cert.sh
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ ! -f .env ]; then
  echo "Нет .env в корне репозитория — скопируйте .env.example и заполните значения." >&2
  exit 1
fi
set -a; source .env; set +a

: "${DOMAIN:?DOMAIN не задан в .env}"
: "${CERTBOT_EMAIL:?CERTBOT_EMAIL не задан в .env}"
: "${BOT_COMPOSE_PROJECT:=yuvibotv2}"
: "${BOT_NGINX_SERVICE:=nginx-https}"

echo "==> Останавливаю $BOT_NGINX_SERVICE (проект $BOT_COMPOSE_PROJECT) на время выпуска сертификата..."
docker compose -p "$BOT_COMPOSE_PROJECT" stop "$BOT_NGINX_SERVICE"

cleanup() {
  echo "==> Поднимаю $BOT_NGINX_SERVICE обратно..."
  docker compose -p "$BOT_COMPOSE_PROJECT" start "$BOT_NGINX_SERVICE"
}
trap cleanup EXIT

echo "==> Запрашиваю сертификат для $DOMAIN (standalone, порт 80)..."
docker run --rm \
  -p 80:80 \
  -v "$(pwd)/deploy/certbot/conf:/etc/letsencrypt" \
  certbot/certbot certonly --standalone \
  -d "$DOMAIN" \
  --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email \
  --non-interactive

# trap выше уже поднимет бота обратно при выходе (в т.ч. если certbot упал)

echo "==> Сертификат получен. Переключаю JiraJura на TLS-конфиг и перезапускаю proxy..."
cp deploy/nginx/proxy.conf.template deploy/nginx/active.conf.template
docker compose -f docker-compose.prod.yml up -d proxy
docker compose -f docker-compose.prod.yml exec proxy nginx -s reload 2>/dev/null || \
  docker compose -f docker-compose.prod.yml restart proxy

echo "==> Готово. Проверьте: curl -Ik https://${DOMAIN}:${HTTPS_PORT:-8443}/"
