#!/usr/bin/env bash
# Первичный выпуск сертификата Let's Encrypt для JiraJura на ВЫДЕЛЕННОМ
# сервере (не делит хост с ботом/другим сервисом) — используется вместо
# issue-cert.sh, тот писан под координацию с чужим nginx на порту 80.
#
# Здесь порт 80 полностью в распоряжении JiraJura (HTTP_PORT=80 в .env),
# поэтому webroot-метод: certbot просто кладёт файл челленджа в общий
# volume (deploy/certbot/www), а его отдаёт уже запущенный proxy — тот
# слушает 80 сам и держит location /.well-known/acme-challenge/ в обоих
# nginx-шаблонах (http-only.conf.template и proxy.conf.template). Никого
# не нужно останавливать — ни на секунду.
#
# Запускать из корня репозитория JiraJura на сервере: ./deploy/scripts/issue-cert-standalone.sh
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ ! -f .env ]; then
  echo "Нет .env в корне репозитория — скопируйте .env.example и заполните значения." >&2
  exit 1
fi
set -a; source .env; set +a

: "${DOMAIN:?DOMAIN не задан в .env}"
: "${CERTBOT_EMAIL:?CERTBOT_EMAIL не задан в .env}"

echo "==> Убедитесь, что proxy уже запущен на HTTP (http-only.conf.template) и HTTP_PORT=80 в .env — иначе challenge никто не отдаст."
echo "==> Запрашиваю сертификат для $DOMAIN (webroot, без остановки proxy)..."
docker compose -f docker-compose.prod.yml run --rm \
  --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN" \
  --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email \
  --non-interactive

echo "==> Сертификат получен. Переключаю JiraJura на TLS-конфиг и перезапускаю proxy..."
cp deploy/nginx/proxy.conf.template deploy/nginx/active.conf.template
docker compose -f docker-compose.prod.yml up -d proxy
# именно restart, не `nginx -s reload`: шаблон из /etc/nginx/templates
# рендерится в конфиг только entrypoint'ом при старте контейнера
docker compose -f docker-compose.prod.yml restart proxy

echo "==> Готово. Проверьте: curl -Ik https://${DOMAIN}/"
