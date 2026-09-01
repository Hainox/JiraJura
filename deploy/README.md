# Деплой JiraJura

Продакшн сейчас — **выделенный сервер** `77.91.94.142` (HostKey, Россия), домен
**`obhod-sao.ru`**. Ничего общего с Telegram-ботом не делит: обычные порты 80/443,
свои DNS-записи, свой хостинг. Все команды ниже выполняются **на сервере по SSH**
(`ssh root@77.91.94.142`) — из песочницы агента прямого доступа по SSH нет.

> Изначально JiraJura запускалась на другом сервере (`82.23.173.215`,
> `journal.yuvibot2.xyz`), деля его с ботом — оттуда нестандартные порты 8080/8443
> в старых заметках/скриптах. 12-13.08.2026 переехали на этот, отдельный сервер.
> Исторические шаги под общий с ботом сервер — в конце файла, раздел «Архив».

## 0. Аудит перед началом (read-only, ничего не меняет)

```bash
echo "--- OS ---"; cat /etc/os-release
echo "--- Docker ---"; docker --version; docker compose version
echo "--- ufw ---"; ufw status verbose
echo "--- Диск/память ---"; df -h /; free -h
```

Проверьте: Docker и Docker Compose v2 установлены, ≥20 ГБ диска свободно.

**Добавьте DNS A-запись** у регистратора домена: `obhod-sao.ru` (и `www.obhod-sao.ru`,
если нужно) → IP сервера. Проверьте: `dig +short obhod-sao.ru` должен вернуть IP сервера.

## 1. Клонирование репозитория

```bash
mkdir -p /opt && cd /opt
git clone https://github.com/Hainox/JiraJura.git jirajura
cd /opt/jirajura
```

## 2. Секреты

```bash
cp .env.example .env
# впишите в .env:
#   DOMAIN=obhod-sao.ru
#   CERTBOT_EMAIL=<ваш email>
#   SECRET_KEY=$(openssl rand -hex 32)
#   POSTGRES_PASSWORD=$(openssl rand -hex 24)
#   HTTP_PORT=80
#   HTTPS_PORT=443
# BOT_COMPOSE_PROJECT/BOT_NGINX_SERVICE — не нужны на выделенном сервере,
# используются только в архивных issue-cert.sh/renew-cert.sh (см. «Архив»).

nano .env   # или любой редактор
```

Быстро сгенерировать и подставить секреты одной командой:
```bash
sed -i 's/^DOMAIN=.*/DOMAIN=obhod-sao.ru/' .env
sed -i 's/^HTTP_PORT=.*/HTTP_PORT=80/' .env
sed -i 's/^HTTPS_PORT=.*/HTTPS_PORT=443/' .env
sed -i "s/^SECRET_KEY=$/SECRET_KEY=$(openssl rand -hex 32)/" .env
sed -i "s/^POSTGRES_PASSWORD=$/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" .env
```

## 3. Файрвол

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
ufw status
```

## 4. Первый запуск (пока без HTTPS — на обычном HTTP:80)

```bash
cp deploy/nginx/http-only.conf.template deploy/nginx/active.conf.template
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
```

Миграции применяются автоматически при старте контейнера `api`
(`backend/docker-entrypoint.sh` перед запуском uvicorn сам гоняет
`alembic upgrade head`) — отдельно вызывать
`docker compose run --rm api alembic upgrade head` не нужно, и это **не
сработает как ожидается**: тот же entrypoint безусловно завершается
`exec uvicorn`, так что такая команда провисит в foreground на запущенном
сервере, пока её не прервут Ctrl+C, вместо того чтобы просто применить
миграции и выйти.

Проверка: `curl -I http://obhod-sao.ru/` должен отдать фронтенд.

### Обновление действующего окружения

Перед применением релиза с унифицированными нарушениями сделайте бэкап и
зафиксируйте текущую ревизию. Миграция relink-ит исторические фотографии, но не
удаляет строки чек-листов, нарушений или файлов.

```bash
cd /opt/jirajura
docker compose -f docker-compose.prod.yml exec db pg_dump -U postgres -Fc sao_inspection > backup-before-unified-issues.dump
git status --short | grep -v '^??' || true   # должно быть пусто — непустой вывод (изменённый
                                              # ОТСЛЕЖИВАЕМЫЙ файл, не считая мусора вроде этого
                                              # же .dump) значит, что кто-то правил файлы руками —
                                              # разберитесь, что именно, прежде чем пуллить поверх
git pull --ff-only
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec api alembic current
```

После обновления создайте один новый обход: чек-лист не должен открываться,
нарушение требует категорию, а статус завершённого обхода определяется по
созданным нарушениям. Затем проверьте «За всё время» (с 01.06.2026) и строку
«ИТОГО» в дашборде, Excel и PPTX.

Заведите первого админа (регистрация только по приглашению, а приглашать пока некому — один раз вручную):
```bash
docker compose -f docker-compose.prod.yml exec db psql -U postgres -d sao_inspection -c "
INSERT INTO users (login, password_hash, full_name, role)
VALUES ('admin', crypt('ВАШ_ПАРОЛЬ', gen_salt('bf')), 'Администратор', 'admin');
"
```
Если `crypt`/`gen_salt` недоступны (нет расширения `pgcrypto`), проще сгенерировать bcrypt-хэш локально и вставить его как `seed.sql`:
```bash
docker compose -f docker-compose.prod.yml exec api python -c "
from app.services.auth import hash_password
print(hash_password('ВАШ_ПАРОЛЬ'))
"
# полученный хэш — в INSERT INTO users (..., password_hash, ...) VALUES (..., '<хэш>', ...)
```
Дальше всех остальных пользователей заводите уже через веб-интерфейс («Пользователи» → «Пригласить») под этим админом.

(Если переносите данные с другого сервера, а не начинаете с нуля — см. `## 8. Перенос данных с другого сервера` ниже, шаги 4-4.4 в этом случае пропускаются.)

## 5. HTTPS

```bash
./deploy/scripts/issue-cert-standalone.sh
```
Certbot получает сертификат методом webroot — кладёт файл челленджа в общий том
`deploy/certbot/www`, который отдаёт уже работающий `proxy` (тот и так слушает 80
сам, не занят ничем чужим). Ничего не нужно останавливать ни на секунду.

Проверка: `curl -Ik https://obhod-sao.ru/`, залогиньтесь в приложении.

Автопродление (раз в сутки; сам certbot продлевает только когда до истечения <30 дней):
```bash
(crontab -l 2>/dev/null; echo "0 3 * * * cd /opt/jirajura && ./deploy/scripts/renew-cert-standalone.sh >> /var/log/jirajura-renew.log 2>&1") | crontab -
```

## 6. Импорт площадок из KML

Площадки заводятся импортом KML-выгрузок (`backend/import_kml.py`). Скрипт уже
входит в образ api, вместе с ним в контейнере есть psycopg2.

1. Скопируйте KML-файлы на сервер (с локальной машины, PowerShell/терминал):
```powershell
ssh root@77.91.94.142 "mkdir -p /opt/jirajura/kml"
scp "C:\путь\к\Детская_площадка.kml" root@77.91.94.142:/opt/jirajura/kml/
scp "C:\путь\к\Спортивная_площадка.kml" root@77.91.94.142:/opt/jirajura/kml/
```

2. Запустите импорт (на сервере, из `/opt/jirajura`):
```bash
docker compose -f docker-compose.prod.yml run --rm \
  -v /opt/jirajura/kml:/kml:ro \
  api python import_kml.py \
  --db-url "postgresql://postgres:$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2)@db:5432/sao_inspection" \
  --kml "/kml/Детская_площадка.kml=Детская площадка" \
  --kml "/kml/Спортивная_площадка.kml=Спортивная площадка" \
  --wipe
```

⚠️ `--wipe` — осознанное подтверждение: импорт **замещает** все площадки/дворы/районы
и удаляет связанные обходы/замечания/фото. Пользователи и чек-листы не трогаются.
Нормально при первичном наполнении; на живой системе с накопленными обходами
сначала сделайте бэкап (см. ниже).

Проверка: обновите приложение в браузере — на карте и во вкладке «Список» должны
появиться площадки.

## 6.1. Массовое приглашение сотрудников

Списки по районам (xlsx, формат: `<Район> — N чел.`, колонки ФИО/Логин/Роль/Телефон)
скачиваются в отдельную папку `rosters/` — она в `.gitignore`, в репозиторий не
попадает, потому что это персональные данные сотрудников (ФИО, телефон).

1. Скопировать xlsx-файлы на сервер:
```powershell
ssh root@77.91.94.142 "mkdir -p /opt/jirajura/rosters"
scp "C:\путь\к\Бескудниковский.xlsx" root@77.91.94.142:/opt/jirajura/rosters/
# ...и так для каждого района
```

2. Сверка без создания приглашений (dry-run — проверяет районы, дубли логинов,
   неизвестные роли, ничего не меняет):
```bash
cd /opt/jirajura
docker compose -f docker-compose.prod.yml run --rm \
  -v /opt/jirajura/rosters:/rosters api python bulk_invite.py \
  --admin-login admin --admin-password 'ПАРОЛЬ_АДМИНА' \
  --xlsx-dir /rosters --out /rosters/result.csv
```

3. Рассылка (создаёт приглашения через тот же API, что и вручную в интерфейсе;
   повторный запуск безопасен — уже приглашённые/зарегистрированные логины
   пропускаются, просроченные приглашения перевыпускаются автоматически):
```bash
docker compose -f docker-compose.prod.yml run --rm \
  -v /opt/jirajura/rosters:/rosters api python bulk_invite.py \
  --admin-login admin --admin-password 'ПАРОЛЬ_АДМИНА' \
  --xlsx-dir /rosters --out /rosters/result.csv --apply
```

4. `rosters/result.csv` — район/ФИО/логин/роль/телефон/статус/**ссылка**;
   ссылки нужно разослать сотрудникам лично (Telegram-бот сознательно не
   интегрирован).

5. После рассылки удалить исходники с сервера (ПДн там больше не нужны):
```bash
rm -rf /opt/jirajura/rosters
```

## 6.2. Переиздание просроченных приглашений и диагностика логинов

Ссылка-приглашение действует 72 часа; если не успели раздать (или человек
не смог зайти), не создавайте новое приглашение вручную под другим
логином — переиздайте существующее (сохраняет логин/ФИО/роль/район,
только новый токен, срок продлевается до 30 дней). Точечно, на одну
запись — прямо из интерфейса («Пользователи» → «Приглашения» → значок
переиздания); массово, по всем/по району — CLI:
```bash
docker compose -f docker-compose.prod.yml exec api python reissue_invites.py                      # dry-run, отчёт
docker compose -f docker-compose.prod.yml exec api python reissue_invites.py --apply --out /app/exports/reissued.csv
docker compose -f docker-compose.prod.yml exec api python reissue_invites.py --district "Сокол" --apply --out /app/exports/reissued_sokol.csv
# скачать CSV с сервера (docker compose ... cp api:/app/exports/reissued.csv .), разослать ссылки, затем удалить файл с сервера (ПДн)
```

⚠️ `--out` всегда в `/app/exports/`, никогда в `/app/uploads/` — та раздаётся
наружу без авторизации через `/uploads/...` (см. `app/services/safe_export.py`,
там же — защита, которая обрывает скрипт, если всё-таки указать `uploads/`).
`exports/` не смонтирована наружу вообще, файлы забираются через
`docker compose ... cp api:/app/exports/<файл> .`, не напрямую с хоста.

Другие разовые скрипты в `backend/` для диагностики после массовой
рассылки — каждый читает БД напрямую (`DATABASE_URL`), запускать так же
через `docker compose ... exec api python <script>.py`:
- `roster_district_status.py` — сверка списка по району с фактической регистрацией
- `diagnose_logins.py` — почему конкретный логин не может зайти (то же самое —
  в интерфейсе, «Разработчик» → «Диагностика», без захода по SSH)
- `verify_invite_links.py` — проверка, что все выданные ссылки рабочие
- `fix_passwords.py` / `reset_shared_passwords.py` — точечный/массовый сброс пароля
- `production_status_report.py` / `generate_summary_report.py` — сводка по округу в консоль/xlsx
- `split_invites_by_district.py` — разбивка результата рассылки по районам для раздачи файлов

## 7. Бэкапы

```bash
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/jirajura/deploy/scripts/backup.sh >> /var/log/jirajura-backup.log 2>&1") | crontab -
```

Дамп БД хранится 14 дней, архив `uploads/` — 2 дня (он дублирует 1:1 то, что и так есть в `backend/uploads/`, и растёт вместе с ним; 12.08.2026 из-за 14-дневного хранения полных копий диск на сервере заполнился до 0 и `db`-контейнер стал unhealthy). Скрипт сам пропускает архивацию `uploads/`, если свободного места меньше полутора его размеров, и пишет об этом в `/var/log/jirajura-backup.log`. Для настоящего офсайт-хранения переносите `db_*.sql.gz`/`uploads_*.tar.gz` за пределы сервера регулярно (вручную/scp), не полагайтесь только на локальные копии на сервере.

## 8. Перенос данных с другого сервера

Если разворачиваете этот сервер как замену другому (перенос БД + фото), после шага 4
(до выпуска HTTPS или после — не важно, только `api`/`db` должны быть подняты):

```bash
# 1. Очистить пустую схему, оставшуюся от alembic:
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d sao_inspection \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 2а. Если старый сервер ещё доступен по SSH — перенос напрямую, без хранения дампа
#     на промежуточном компьютере (быстрее и надёжнее для больших объёмов):
ssh root@<старый_сервер> "docker compose -f /opt/jirajura/docker-compose.prod.yml exec -T db pg_dump -U postgres sao_inspection" \
  | docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d sao_inspection
ssh root@<старый_сервер> "tar -czf - -C /opt/jirajura/backend/uploads ." \
  | tar -xzf - -C backend/uploads

# 2б. Либо восстановить из локального файла дампа (db_*.sql.gz с бэкапа):
gunzip -c db_ВРЕМЯ.sql.gz | docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d sao_inspection

# 3. Перезапустить api и сверить счётчики:
docker compose -f docker-compose.prod.yml restart api
docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d sao_inspection -c "
SELECT 'districts' t, count(*) FROM districts
UNION ALL SELECT 'sites', count(*) FROM sites
UNION ALL SELECT 'users', count(*) FROM users
UNION ALL SELECT 'inspections', count(*) FROM inspections
UNION ALL SELECT 'issues', count(*) FROM issues
UNION ALL SELECT 'photos', count(*) FROM photos;
"
```

Долгие переносы (десятки ГБ) лучше делать в `tmux`/`screen` на сервере — обрыв SSH
не оборвёт саму передачу:
```bash
apt install -y tmux
tmux new -s transfer
# ...команда переноса...
# Ctrl+B, затем D — отсоединиться, не прерывая; вернуться: tmux attach -t transfer
```

⚠️ Команды выше выполняются **на новом сервере**, а не на старом и не на локальном
компьютере — перепутать легко, если работаете сразу в нескольких SSH-окнах.
После переноса не забудьте сравнить пароль root старого сервера как
скомпрометированный (если он где-то засветился при передаче) и сменить его
(`passwd`), раз сервер выводится из эксплуатации.

## 9. Обновление после изменений в репозитории

```bash
cd /opt/jirajura
git status --short | grep -v '^??' || true   # должно быть пусто (незакоммиченные файлы вроде
                      # .deploy-watcher-state — не в счёт). Непустой вывод значит, что кто-то
                      # правил ОТСЛЕЖИВАЕМЫЕ файлы прямо на сервере мимо git; git pull может либо
                      # упасть на конфликте, либо (если изменённый файл не задет входящими
                      # коммитами) молча пройти и оставить в следующей сборке чужой
                      # незакоммиченный код вместо актуального main
git pull --ff-only origin main
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

Миграции применяет сам контейнер `api` при старте — `docker-entrypoint.sh`
гоняет `alembic upgrade head` перед запуском uvicorn на каждом старте
контейнера, повторный прогон безопасен (все миграции идемпотентны). Отдельно
вызывать `docker compose run --rm api alembic upgrade head` **не нужно и не
сработает как ожидается**: entrypoint безусловно завершается `exec uvicorn`
после миграций, так что такая команда не завершится сама — провиснет в
foreground на запущенном сервере, пока её не прервут Ctrl+C. Проверить
применённую ревизию: `docker compose -f docker-compose.prod.yml exec api alembic current`.

`deploy/nginx/proxy.conf.template` использует Docker DNS-резолвер
(`resolver 127.0.0.11 valid=10s;` + `set $api_upstream` + явный `$request_uri` в
`proxy_pass`) — nginx сам переоткрывает соединение на актуальный IP `api`/`frontend`
в течение ~10 секунд после пересборки, отдельный `restart proxy` для этого не нужен.
Перезапускать `proxy` вручную нужно, только если менялся сам
`proxy.conf.template`/`http-only.conf.template`.

## 10. Деплой по клику из веб-интерфейса («Разработчик» → «Деплой»)

Раздел «Разработчик» (доступен только вашему аккаунту — `is_developer=true`,
см. «Пользователи») умеет отправлять запрос на редеплой прямо из браузера,
без захода по SSH. Сам API-контейнер ничего не исполняет на хосте (не имеет
доступа ни к docker-сокету, ни к файлам вне себя) — кнопка только пишет
маркер в БД (`audit_log`, `action='deploy_requested'`). Реальные команды
(`git pull && build && up -d` — тот же набор, что и в п.9 выше; миграции
применяются автоматически контейнером `api` при старте, отдельного
`alembic upgrade head` в этой последовательности намеренно нет — см. п.9)
выполняет отдельный скрипт на хосте, который нужно один раз поставить в cron:

```bash
(crontab -l 2>/dev/null; echo "* * * * * bash /opt/jirajura/deploy/scripts/deploy-watcher.sh >> /var/log/jirajura-deploy-watcher.log 2>&1") | crontab -
```
(запуск через `bash ...`, а не `./...` — файл, добавленный через API, не приносит с собой исполняемый бит; при желании можно один раз `chmod +x deploy/scripts/deploy-watcher.sh` и убрать `bash` из команды, но это не обязательно)

Раз в минуту скрипт проверяет, не появился ли новый маркер, и если да —
выполняет обновление и пишет результат (успех/провал + хвост лога) обратно
в `audit_log` (`action='deploy_completed'`) — результат виден в самом
разделе «Разработчик» в приложении. Состояние («что уже обработано») —
локальный файл `/opt/jirajura/.deploy-watcher-state`, не путать с бэкапами,
удалять не нужно.

Первый запуск стоит проверить вручную, не дожидаясь cron:
```bash
cd /opt/jirajura
bash deploy/scripts/deploy-watcher.sh   # без маркеров — молча завершится, это нормально
```

Так же вручную можно посмотреть, что скрипт видит и как считает маркеры:
```bash
docker compose -f docker-compose.prod.yml exec -T api python list_deploy_requests.py --since 1970-01-01T00:00:00+00:00
```

⚠️ Файл `.deploy-watcher-state` создаётся автоматически при первом запуске;
если его удалить, следующий запуск заново обработает все прошлые маркеры
из истории — это безвредно (git pull/build/up идемпотентны), но лишний
прогон деплоя лучше не устраивать без повода.

---

## Архив: сервер, общий с Telegram-ботом

Исторические шаги для первого сервера JiraJura (`82.23.173.215`, `journal.yuvibot2.xyz`),
где 80/443 были заняты чужим nginx-контейнером бота (`yuvibotv2-nginx-https-1`).
Актуально, только если когда-нибудь понадобится развернуть JiraJura рядом с другим
сервисом на общем сервере — на текущем продакшене (раздел выше) не используется.

- Порты наружу — не 80/443, а `HTTP_PORT=8080`/`HTTPS_PORT=8443` в `.env`.
- HTTPS — `./deploy/scripts/issue-cert.sh` / `renew-cert.sh` (не `-standalone` версии):
  используют certbot в режиме `--standalone`, для чего на несколько секунд
  останавливают nginx-контейнер соседа (`docker compose -p $BOT_COMPOSE_PROJECT stop
  $BOT_NGINX_SERVICE`), получают сертификат, поднимают его обратно. Имя
  compose-проекта и сервиса соседа — в `.env` (`BOT_COMPOSE_PROJECT`/`BOT_NGINX_SERVICE`).
- Файрвол: на том сервере `ufw` не был установлен — порты бота и так были открыты
  всему интернету напрямую через Docker (Docker сам управляет `iptables` в обход
  хостового файрвола). Если переиспользуете этот сценарий на новом общем сервере,
  учитывайте то же самое или настраивайте `ufw-docker`/правила в цепочке
  `DOCKER-USER` отдельно.
- До и после каждого шага (особенно после `issue-cert.sh`/`renew-cert.sh`)
  отправляйте соседнему сервису тестовый запрос — должен отвечать как обычно.
  `docker ps` — контейнеры `jirajura-*` не должны пересекаться именами/портами
  с контейнерами соседа.
