#!/usr/bin/env bash
# Подключает сайт «Люки САО» (luki.obhod-sao.ru) к proxy журнала обходов:
# выпускает сертификат, если его ещё нет, и включает server-блок
# deploy/nginx/sites/luki-sao.conf симлинком в deploy/nginx/sites-enabled/.
# Повторный запуск безопасен. Продление — общим renew-cert*.sh (certbot
# renew продлевает все сертификаты).
#
# Запускать из корня репозитория JiraJura на сервере: ./deploy/scripts/enable-luki-sao.sh
set -euo pipefail
cd "$(dirname "$0")/../.."

LUKI_DOMAIN=luki.obhod-sao.ru
COMPOSE="docker compose -f docker-compose.prod.yml"

if [ ! -f .env ]; then
  echo "Нет .env в корне репозитория." >&2
  exit 1
fi
set -a; source .env; set +a
: "${CERTBOT_EMAIL:?CERTBOT_EMAIL не задан в .env}"

# Каталоги sites/sites-enabled и include в шаблоне появляются в proxy только
# после деплоя журнала обходов с этими правками — без него сайт молча не
# включился бы.
if ! grep -Fq 'sites-enabled' deploy/nginx/active.conf.template 2>/dev/null; then
  echo "В deploy/nginx/active.conf.template нет include sites-enabled — сначала задеплойте журнал обходов (кнопка «Деплой»)." >&2
  exit 1
fi

if [ ! -f "deploy/certbot/conf/live/$LUKI_DOMAIN/fullchain.pem" ]; then
  echo "==> Запрашиваю сертификат для $LUKI_DOMAIN (webroot через работающий proxy)..."
  $COMPOSE run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
    -d "$LUKI_DOMAIN" \
    --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email \
    --non-interactive
fi

ln -sfn ../sites/luki-sao.conf deploy/nginx/sites-enabled/luki-sao.conf

if ! $COMPOSE exec -T proxy test -e /etc/nginx/sites-enabled/luki-sao.conf; then
  rm -f deploy/nginx/sites-enabled/luki-sao.conf
  echo "proxy не видит deploy/nginx/sites-enabled — контейнер запущен со старыми томами. Сначала задеплойте журнал обходов (кнопка «Деплой»)." >&2
  exit 1
fi

# Проверяем конфиг в уже запущенном proxy: если что-то не так, выключаем
# сайт обратно, чтобы следующий деплой журнала обходов не споткнулся о
# nginx -t.
if ! $COMPOSE exec -T proxy nginx -t; then
  rm -f deploy/nginx/sites-enabled/luki-sao.conf
  echo "nginx -t не прошёл — сайт $LUKI_DOMAIN выключен обратно, proxy не тронут." >&2
  exit 1
fi
$COMPOSE exec -T proxy nginx -s reload

echo "==> Готово. Проверьте: curl -I https://$LUKI_DOMAIN/"
echo "    502 — сайт подключён, но «Люки САО» ещё не запущены (/opt/luki-sao)."
