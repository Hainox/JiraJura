#!/usr/bin/env bash
# Забирает маркеры "запрошен деплой" (кнопка «Деплой» в разделе
# «Разработчик» в приложении → POST /api/v1/system/deploy/request пишет
# action='deploy_requested' в audit_log) и выполняет тот же фиксированный
# набор команд, что и ручное обновление по README.md, п.9 — git pull,
# build, up -d, alembic upgrade head. Ничего произвольного не исполняет —
# набор команд задан прямо в этом файле, не приходит из БД/сети.
#
# api НЕ имеет доступа ни к docker-сокету, ни к этому файлу — весь обмен
# с ним идёт только через строки в audit_log (list_deploy_requests.py /
# record_deploy_result.py, оба — backend/*.py). Скрипт запускается на
# хосте, вне контейнеров.
#
# Установка на сервере (см. README.md, п.10):
#   * * * * * /opt/jirajura/deploy/scripts/deploy-watcher.sh >> /var/log/jirajura-deploy-watcher.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/../.."   # /opt/jirajura

STATE_FILE=".deploy-watcher-state"
LOCK_FILE="/tmp/jirajura-deploy-watcher.lock"
COMPOSE="docker compose -f docker-compose.prod.yml"

# flock — если предыдущий запуск (деплой занял больше минуты) ещё не
# закончился, не стартуем второй параллельный.
exec 9>"$LOCK_FILE"
flock -n 9 || { echo "$(date -Iseconds) уже выполняется — пропуск"; exit 0; }

LAST_SEEN=$(cat "$STATE_FILE" 2>/dev/null || echo "1970-01-01T00:00:00+00:00")

MARKERS=$($COMPOSE exec -T api python list_deploy_requests.py --since "$LAST_SEEN")
if [ -z "$MARKERS" ]; then
  exit 0
fi

NEW_LAST_SEEN="$LAST_SEEN"
while IFS=$'\t' read -r ENTITY_ID CREATED_AT; do
  [ -z "$ENTITY_ID" ] && continue
  echo "$(date -Iseconds) обрабатываю деплой, запрошенный $CREATED_AT (entity_id=$ENTITY_ID)"

  LOG_TMP=$(mktemp)
  if {
    git pull --ff-only origin main
    $COMPOSE build
    $COMPOSE up -d
    $COMPOSE run --rm api alembic upgrade head
  } >"$LOG_TMP" 2>&1; then
    STATUS_FLAG=--ok
  else
    STATUS_FLAG=--fail
  fi

  # api-контейнер после build+up -d уже новый — это ожидаемо и не мешает:
  # record_deploy_result.py не зависит от версии кода, только от схемы БД.
  $COMPOSE exec -T api python record_deploy_result.py --entity-id "$ENTITY_ID" $STATUS_FLAG < "$LOG_TMP"

  echo "$(date -Iseconds) деплой $ENTITY_ID завершён ($STATUS_FLAG)"
  cat "$LOG_TMP"
  rm -f "$LOG_TMP"

  NEW_LAST_SEEN="$CREATED_AT"
done <<< "$MARKERS"

echo "$NEW_LAST_SEEN" > "$STATE_FILE"
