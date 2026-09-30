#!/usr/bin/env bash
# Сайт «Люки САО» на общем proxy: server-блок в репозитории, включение —
# только симлинком после выпуска сертификата (без сертификата nginx -t не
# проходит, и деплой журнала обходов остановился бы на проверке конфига).
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
site="$root/deploy/nginx/sites/luki-sao.conf"
compose="$root/docker-compose.prod.yml"
enable="$root/deploy/scripts/enable-luki-sao.sh"

grep -Fq 'server_name luki.obhod-sao.ru;' "$site"
grep -Fq '/etc/letsencrypt/live/luki.obhod-sao.ru/fullchain.pem' "$site"
grep -Fq 'set $luki_upstream luki-web:8080;' "$site"
grep -Fq 'proxy_pass http://$luki_upstream$request_uri;' "$site"
grep -Fq 'proxy_set_header X-Real-IP $remote_addr;' "$site"
grep -Fq 'resolver 127.0.0.11' "$site"

grep -Fq 'include /etc/nginx/sites-enabled/*.conf;' "$root/deploy/nginx/proxy.conf.template"
# В http-only (до выпуска основного сертификата) сайтов с TLS быть не может.
if grep -Fq 'sites-enabled' "$root/deploy/nginx/http-only.conf.template"; then exit 1; fi

grep -Fq './deploy/nginx/sites:/etc/nginx/sites:ro' "$compose"
grep -Fq './deploy/nginx/sites-enabled:/etc/nginx/sites-enabled:ro' "$compose"

# В репозитории сайт не включён: иначе деплой на сервере без сертификата
# luki.obhod-sao.ru падал бы на nginx -t.
test -z "$(git -C "$root" ls-files 'deploy/nginx/sites-enabled/*.conf')"
grep -Fq 'deploy/nginx/sites-enabled/*' "$root/.gitignore"

grep -Fq 'ln -sfn ../sites/luki-sao.conf deploy/nginx/sites-enabled/luki-sao.conf' "$enable"
grep -Fq 'nginx -t' "$enable"
grep -Fq 'test -e /etc/nginx/sites-enabled/luki-sao.conf' "$enable"
grep -Fq 'certonly --webroot' "$enable"
grep -Fq 'test_luki_proxy_config.sh' "$root/.github/workflows/ci.yml"
grep -Fq 'luki.obhod-sao.ru' "$root/deploy/README.md"
