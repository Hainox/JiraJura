# Деплой JiraJura на сервер (изолированно от Telegram-бота)

Сервер: `82.23.173.215`, домен для JiraJura: **`journal.yuvibot2.xyz`** (поддомен `yuvibot2.xyz` — сам `yuvibot2.xyz` уже занят Mini App бота). Все команды ниже выполняются **на сервере по SSH** (`ssh root@82.23.173.215`) — из песочницы агента прямого доступа по SSH нет.

## 0. Аудит перед началом (read-only, ничего не меняет)

```bash
echo "--- OS ---"; cat /etc/os-release
echo "--- Docker ---"; docker --version; docker compose version
echo "--- Все контейнеры (включая бота) ---"; docker ps -a
echo "--- Слушающие порты ---"; ss -tulpn
echo "--- ufw ---"; ufw status verbose
echo "--- Диск/память ---"; df -h /; free -h
```

Проверьте: контейнер бота `yuvibotv2-nginx-https-1` (или похожий) слушает 80/443; 8080/8443 свободны; ≥20 ГБ диска свободно.

**Добавьте DNS A-запись** у вашего DNS-провайдера домена `yuvibot2.xyz`: `journal` → `82.23.173.215`. Проверьте, что применилась: `dig +short journal.yuvibot2.xyz` (или `ping journal.yuvibot2.xyz`) должен вернуть `82.23.173.215`.

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
#   CERTBOT_EMAIL=<ваш email>
#   SECRET_KEY=$(openssl rand -hex 32)
#   POSTGRES_PASSWORD=$(openssl rand -hex 24)
# DOMAIN/HTTP_PORT/HTTPS_PORT/BOT_COMPOSE_PROJECT/BOT_NGINX_SERVICE уже
# заполнены правильными значениями по умолчанию — менять не нужно, если
# у бота действительно проект "yuvibotv2" и сервис "nginx-https"
# (проверьте по выводу `docker ps` из шага 0).

nano .env   # или любой редактор
```

Быстро сгенерировать и подставить секреты одной командой:
```bash
sed -i "s/^SECRET_KEY=$/SECRET_KEY=$(openssl rand -hex 32)/" .env
sed -i "s/^POSTGRES_PASSWORD=$/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" .env
```

## 3. Первый запуск (пока без HTTPS — на HTTP:8080)

```bash
cp deploy/nginx/http-only.conf.template deploy/nginx/active.conf.template
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml ps
```

Проверка: `curl -I http://journal.yuvibot2.xyz:8080/` должен отдать фронтенд.

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

## 4. HTTPS

```bash
./deploy/scripts/issue-cert.sh
```
Скрипт сам: остановит nginx-контейнер бота на несколько секунд → получит сертификат Let's Encrypt → вернёт бота → переключит JiraJura на TLS-конфиг. Бот при этом ни разу не перезапускается «жёстко» — только `stop`/`start` того же контейнера, без изменения его файлов.

Проверка: `curl -Ik https://journal.yuvibot2.xyz:8443/`, залогиньтесь в приложении под заведённым админом.

Автопродление (раз в сутки; сам certbot продлевает только когда до истечения <30 дней):
```bash
(crontab -l 2>/dev/null; echo "0 3 * * * cd /opt/jirajura && ./deploy/scripts/renew-cert.sh >> /var/log/jirajura-renew.log 2>&1") | crontab -
```

## 4.5. Импорт площадок из KML

Площадки заводятся импортом KML-выгрузок (`backend/import_kml.py`). Скрипт уже
входит в образ api, вместе с ним в контейнере есть psycopg2.

1. Скопируйте KML-файлы на сервер (с локальной машины, PowerShell/терминал):
```powershell
ssh root@82.23.173.215 "mkdir -p /opt/jirajura/kml"
scp "C:\путь\к\Детская_площадка.kml" root@82.23.173.215:/opt/jirajura/kml/
scp "C:\путь\к\Спортивная_площадка.kml" root@82.23.173.215:/opt/jirajura/kml/
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

## 4.6. Массовое приглашение сотрудников

Списки по районам (xlsx, формат: `<Район> — N чел.`, колонки ФИО/Логин/Роль/Телефон)
скачиваются в отдельную папку `rosters/` — она в `.gitignore`, в репозиторий не
попадает, потому что это персональные данные сотрудников (ФИО, телефон).

1. Скопировать xlsx-файлы на сервер:
```powershell
ssh root@82.23.173.215 "mkdir -p /opt/jirajura/rosters"
scp "C:\путь\к\Бескудниковский.xlsx" root@82.23.173.215:/opt/jirajura/rosters/
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
   интегрирован — см. план деплоя, часть B).

5. После рассылки удалить исходники с сервера (ПДн там больше не нужны):
```bash
rm -rf /opt/jirajura/rosters
```

## 4.7. Переиздание просроченных приглашений и диагностика логинов

Ссылка-приглашение действует 72 часа; если не успели раздать (или человек
не смог зайти), не создавайте новое приглашение вручную под другим
логином — переиздайте существующее (сохраняет логин/ФИО/роль/район,
только новый токен, срок продлевается до 30 дней):
```bash
docker compose -f docker-compose.prod.yml exec api python reissue_invites.py                      # dry-run, отчёт
docker compose -f docker-compose.prod.yml exec api python reissue_invites.py --apply --out /app/uploads/reissued.csv
docker compose -f docker-compose.prod.yml exec api python reissue_invites.py --district "Сокол" --apply --out /app/uploads/reissued_sokol.csv
# скачать CSV с сервера, разослать ссылки, затем удалить файл с сервера (ПДн)
```

Другие разовые скрипты в `backend/` для диагностики после массовой
рассылки — каждый читает БД напрямую (`DATABASE_URL`), запускать так же
через `docker compose ... exec api python <script>.py`:
- `roster_district_status.py` — сверка списка по району с фактической регистрацией
- `diagnose_logins.py` — почему конкретный логин не может зайти
- `verify_invite_links.py` — проверка, что все выданные ссылки рабочие
- `fix_passwords.py` / `reset_shared_passwords.py` — точечный/массовый сброс пароля
- `production_status_report.py` / `generate_summary_report.py` — сводка по округу в консоль/xlsx
- `split_invites_by_district.py` — разбивка результата рассылки по районам для раздачи файлов

## 5. Бэкапы

```bash
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/jirajura/deploy/scripts/backup.sh >> /var/log/jirajura-backup.log 2>&1") | crontab -
```

## 6. Файрвол

На этом сервере `ufw` не установлен — порты бота (80/443/8002/8003) и так открыты всему интернету напрямую через Docker (Docker сам управляет `iptables` в обход хостового файрвола, так что даже установка `ufw` не закрыла бы уже опубликованные Docker-портыт без дополнительной настройки под Docker). Порты JiraJura (8080/8443) будут открыты ровно так же, как и у бота, — отдельных действий на этом шаге не требуется.

Если хотите реально ограничить доступ (например, только определённые порты/IP наружу) — это делается либо через файрвол в панели облачного провайдера (фильтрует ещё до попадания трафика на сервер, не обходится Docker'ом), либо через `ufw` + `ufw-docker`/правила в цепочке `DOCKER-USER` (сложнее, отдельная задача, не блокирует запуск JiraJura).

## 7. Обновление после изменений в репозитории

```bash
cd /opt/jirajura
git pull origin main
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
```

`deploy/nginx/proxy.conf.template` использует Docker DNS-резолвер
(`resolver 127.0.0.11 valid=10s;` + `set $api_upstream`) — nginx сам
переоткрывает соединение на актуальный IP `api`/`frontend` в течение ~10
секунд после пересборки, отдельный `restart proxy` для этого больше не
нужен. Перезапускать `proxy` вручную нужно, только если менялся сам
`proxy.conf.template`/`http-only.conf.template`.

## Проверка, что бот не пострадал

До и после каждого шага (особенно после `issue-cert.sh`/`renew-cert.sh`) отправьте боту сообщение в Telegram — должен ответить как обычно. `docker ps` — контейнеры `jirajura-*` не пересекаются именами/портами с `yuvibotv2-*`.
