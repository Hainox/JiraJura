#!/usr/bin/env bash
# Ночной бэкап БД + загруженных фото. Вызывается из cron, см. deploy/README.md.
set -euo pipefail
cd "$(dirname "$0")/../.."

STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$(pwd)/backups"
mkdir -p "$BACKUP_DIR"

docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U postgres sao_inspection | gzip > "$BACKUP_DIR/db_${STAMP}.sql.gz"

tar -czf "$BACKUP_DIR/uploads_${STAMP}.tar.gz" -C backend uploads

# Локальная ротация — храним 14 дней. Для внеофисного хранения добавьте сюда
# rclone/rsync выгрузку db_*/uploads_* во внешнее хранилище.
find "$BACKUP_DIR" -type f -mtime +14 -delete

echo "$(date -Is) backup.sh: OK ($BACKUP_DIR/db_${STAMP}.sql.gz, uploads_${STAMP}.tar.gz)"
