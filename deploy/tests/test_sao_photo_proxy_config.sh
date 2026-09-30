#!/usr/bin/env bash
# Маршрут фото-сервиса (/photo-api/) должен жить в репозитории целиком: 30.09.2026
# ручная правка active.conf.template на сервере была стёрта обычным деплоем
# (cp proxy.conf.template → active.conf.template), и /photo-api/ пропал.
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
snippet="$root/deploy/nginx/sao-photo-location.conf"
compose="$root/docker-compose.prod.yml"

grep -Fq 'location /photo-api/' "$snippet"
grep -Fq 'set $sao_photo_upstream sao-photo-service-api:8788;' "$snippet"
grep -Fq 'proxy_pass http://$sao_photo_upstream$uri$is_args$args;' "$snippet"
grep -Fq 'include /etc/nginx/sao-photo-location.conf;' "$root/deploy/nginx/proxy.conf.template"
grep -Fq 'include /etc/nginx/sao-photo-location.conf;' "$root/deploy/nginx/http-only.conf.template"
grep -Fq './deploy/nginx/sao-photo-location.conf:/etc/nginx/sao-photo-location.conf:ro' "$compose"
grep -Fq 'name: sao-photo-service-edge' "$compose"
grep -Fq 'sao_photo_edge: {}' "$compose"
grep -Fq 'sao-photo-location.conf' "$root/.github/workflows/ci.yml"
grep -Fq 'sao-photo-service-edge' "$root/deploy/README.md"
