#!/usr/bin/env bash
# Забирает маркеры "запрошен деплой" (кнопка «Деплой» в разделе
# «Разработчик» в приложении → POST /api/v1/system/deploy/request пишет
# action='deploy_requested' в audit_log) и выполняет тот же фиксированный
# набор команд, что и ручное обновление по README.md, п.9 — git pull,
# build, up -d (миграции применяет сам контейнер api при старте, см.
# docker-entrypoint.sh — отдельный `alembic upgrade head` не нужен и не
# сработает как отдельная команда, см. п.9 README.md). Ничего произвольного
# не исполняет — набор команд задан прямо в этом файле, не приходит из БД/сети.
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
  if (
    # Отслеживаемые файлы должны быть чистыми перед pull — иначе git pull может
    # либо упасть (если правленный файл конфликтует с входящим коммитом), либо,
    # что опаснее, молча пройти (если не конфликтует) и оставить в образе
    # чей-то незакоммиченный локальный правленный файл вместо кода из main.
    # Ровно так один раз сломался /issues/categories на проде: кто-то правил
    # backend/app/routers/issues.py прямо на сервере, не через git, изменения
    # остались незакоммиченными и попали в собранный образ.
    #
    # `grep -v '^??'` отфильтровывает НЕотслеживаемые файлы (в т.ч. этот же
    # .deploy-watcher-state, который скрипт сам пишет в корень репозитория,
    # а также любые чужие CSV/dump-выгрузки, которые кто-то оставит в
    # /opt/jirajura) — они не участвуют в git pull и не попадают в образ
    # (Dockerfile копирует только backend/**, а не корень репозитория), так
    # что не должны блокировать деплой. Опасны именно ИЗМЕНЁННЫЕ отслеживаемые
    # файлы — их и проверяем.
    DIRTY=$(git status --short | grep -v '^??' || true)
    if [ -n "$DIRTY" ]; then
      echo "Рабочая копия не чистая — деплой отменён, нужно разобраться руками (git status/git diff):"
      echo "$DIRTY"
      exit 1
    fi
    git pull --ff-only origin main
    $COMPOSE build
    $COMPOSE up -d

    # deploy/nginx/active.conf.template — не отслеживаемая git'ом копия
    # proxy.conf.template (переключается один раз при выпуске сертификата,
    # см. issue-cert-standalone.sh) — git pull её никогда не трогает. Если
    # proxy.conf.template в репозитории с тех пор поменялся (например, порт
    # frontend 80→8080 в PR #140), active.conf.template тихо расходится с
    # ним и держит сайт недоступным (502) до тех пор, пока кто-то не
    # заметит и не пересоздаст его руками — так уже один раз положило прод
    # с самого утра. Синхронизируем на каждом деплое, но только когда прод
    # уже на TLS (ssl_certificate есть только в proxy.conf.template, не в
    # http-only.conf.template) — иначе на первичной установке, до выпуска
    # сертификата, затёрли бы бутстрап-конфиг конфигом, ссылающимся на ещё
    # не существующие файлы сертификата, и proxy вовсе не стартовал бы.
    if grep -q 'ssl_certificate' deploy/nginx/active.conf.template 2>/dev/null; then
      cp deploy/nginx/proxy.conf.template deploy/nginx/active.conf.template
    fi
    # up -d выше не пересоздаёт proxy, если его секция в
    # docker-compose.prod.yml не менялась — а шаблон рендерится
    # entrypoint'ом ТОЛЬКО при старте контейнера. Без явного restart
    # обновлённый active.conf.template до nginx не долетит, даже если
    # строка выше его только что переписала.
    $COMPOSE restart proxy
  ) >"$LOG_TMP" 2>&1; then
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
