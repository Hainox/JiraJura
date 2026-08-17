#!/usr/bin/env bash
# Ночной бэкап БД + загруженных фото. Вызывается из cron, см. deploy/README.md.
set -euo pipefail
cd "$(dirname "$0")/../.."

STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$(pwd)/backups"
mkdir -p "$BACKUP_DIR"

# Полный архив uploads/ на том же диске, где и сам uploads/, — если места
# впритык, следующий tar может забить диск до 0 и уронить Postgres (уже
# случалось: db-контейнер уходил в unhealthy, потому что писать было
# некуда). Останавливаемся заранее, если свободно меньше, чем сам uploads/
# весит с запасом на рост — тогда только дамп БД (маленький) всё равно
# снимется, а тяжёлую часть пропускаем и громко предупреждаем в лог/cron-письмо.
UPLOADS_SIZE_KB=$(du -sk backend/uploads | cut -f1)
AVAIL_KB=$(df -Pk "$BACKUP_DIR" | awk 'NR==2 {print $4}')
NEEDED_KB=$((UPLOADS_SIZE_KB * 3 / 2))

docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U postgres sao_inspection | gzip > "$BACKUP_DIR/db_${STAMP}.sql.gz"

if [ "$AVAIL_KB" -lt "$NEEDED_KB" ]; then
  echo "$(date -Is) backup.sh: ПРОПУЩЕН архив uploads/ — свободно $((AVAIL_KB / 1024 / 1024))G, нужно ~$((NEEDED_KB / 1024 / 1024))G. Снят только дамп БД. Освободите место (docker builder prune, старые backups/uploads_*.tar.gz) и проверьте диск." >&2
else
  # GNU tar возвращает 1 (не 0), если файл изменился прямо во время чтения —
  # штатная ситуация для живой uploads/, куда инспекторы льют фото 24/7,
  # архив при этом получается рабочим. Под "set -e" код 1 без этой обвязки
  # прерывал бы скрипт ДО ротации ниже — именно так уже "тихо" отключалась
  # чистка старых архивов (см. комментарий про 12.08.2026). Код ≥2 — уже
  # настоящая ошибка (диск кончился на середине записи и т.п.), тут по-прежнему валимся.
  set +e
  tar -czf "$BACKUP_DIR/uploads_${STAMP}.tar.gz" -C backend uploads
  tar_rc=$?
  set -e
  if [ "$tar_rc" -gt 1 ]; then
    echo "$(date -Is) backup.sh: tar завершился с кодом $tar_rc — архив uploads/ мог получиться битым." >&2
    exit "$tar_rc"
  fi
fi

# Ротация: дамп БД маленький — храним 14 дней. Архив uploads/ дублирует
# 1:1 то, что и так цело в backend/uploads/, и растёт вместе с ним — при
# 14-дневном хранении полных копий это гарантированно забивает диск
# (ровно так уже произошло 12.08.2026). Держим только 2 последних дня —
# для настоящего офсайт-хранения переносите db_*/uploads_* за пределы
# этого сервера (rclone/rsync/scp), а не увеличивайте это число.
find "$BACKUP_DIR" -name 'db_*.sql.gz' -type f -mtime +14 -delete
find "$BACKUP_DIR" -name 'uploads_*.tar.gz' -type f -mtime +2 -delete

echo "$(date -Is) backup.sh: OK ($BACKUP_DIR/db_${STAMP}.sql.gz)"

