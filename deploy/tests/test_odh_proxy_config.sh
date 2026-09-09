#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
snippet="$root/deploy/nginx/odh-api.conf.template"

grep -Fq 'location /odh-api/' "$snippet"
grep -Fq 'set $odh_api_upstream odh-sao-api:8787;' "$snippet"
grep -Fq 'proxy_pass http://$odh_api_upstream$uri$is_args$args;' "$snippet"
grep -Fq 'include /etc/nginx/conf.d/odh-api.conf;' "$root/deploy/nginx/proxy.conf.template"
grep -Fq 'include /etc/nginx/conf.d/odh-api.conf;' "$root/deploy/nginx/http-only.conf.template"
grep -Fq './deploy/nginx/odh-api.conf.template:/etc/nginx/templates/odh-api.conf.template:ro' "$root/docker-compose.prod.yml"
grep -Fq 'ODH_HEALTH_PATH' "$root/deploy/scripts/verify-odh-proxy.sh"
grep -Fq 'verify-odh-proxy.sh' "$root/deploy/scripts/deploy-watcher.sh"
grep -Fq 'jirajura_default' "$root/deploy/README.md"
