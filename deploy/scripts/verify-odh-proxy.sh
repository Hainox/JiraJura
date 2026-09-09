#!/usr/bin/env bash
# Проверяет ODH API через публичный reverse proxy, не раскрывая порт API
# наружу. Путь задаётся владельцем ODH в .env, поскольку JiraJura не знает
# контракт отдельного сервиса.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

read_env() {
  local key="$1"
  [ -f "$ENV_FILE" ] || return 0
  sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1
}

DOMAIN="$(read_env DOMAIN)"
ODH_HEALTH_PATH="$(read_env ODH_HEALTH_PATH)"

if [ -z "$DOMAIN" ]; then
  echo "ODH proxy: DOMAIN не задан в .env" >&2
  exit 2
fi

if [ -z "$ODH_HEALTH_PATH" ]; then
  echo "ODH proxy: проверка пропущена (ODH_HEALTH_PATH не задан)"
  exit 0
fi

case "$ODH_HEALTH_PATH" in
  /*) ;;
  *)
    echo "ODH proxy: ODH_HEALTH_PATH должен начинаться с /" >&2
    exit 2
    ;;
esac

curl --fail --silent --show-error "https://${DOMAIN}/odh-api${ODH_HEALTH_PATH}"
