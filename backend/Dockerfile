FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY alembic.ini .
COPY schema.sql .
# Разовые эксплуатационные скрипты в корне backend/ (диагностика логинов,
# рассылка приглашений, сверка списков и т.п.) — копируем всё разом, чтобы
# не забывать вручную дописывать сюда каждый новый скрипт (это уже дважды
# приводило к "No such file or directory" на проде, см. историю).
COPY *.py ./
COPY *.csv ./
COPY alembic/ ./alembic/
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh && mkdir -p /app/uploads

# Непривилегированный пользователь — контейнер обрабатывает произвольные
# загружаемые фото (issues.py/inspections.py/feedback.py), и запуск от root
# без нужды расширяет последствия любого будущего RCE в обработке загрузок.
# Фиксированный UID/GID (не 1000 — легко случайно совпадает с реальным
# пользователем на хосте). Это только создание пользователя и chown
# образа "на всякий случай" (пригодится, если кто-то когда-нибудь запустит
# контейнер вовсе без bind mount на /app/uploads) — сам контейнер СТАРТУЕТ
# от root и намеренно НЕ переключается сюда через USER: реальный
# bind-mount backend/uploads (и prod, и dev docker-compose.yml — оба
# монтируют host-каталог поверх /app/uploads) при первом старте с этим
# релизом ещё принадлежит старому владельцу, а docker-entrypoint.sh чинит
# его перед тем, как перейти на appuser — см. там.
RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -M -s /usr/sbin/nologin appuser \
    && chown -R appuser:appgroup /app

EXPOSE 8000
# Миграции применяются автоматически на старте контейнера
# (docker-entrypoint.sh), а не отдельной ручной командой после деплоя —
# "alembic upgrade head" уже трижды забывали прогнать после git pull/build/up
# на проде, и код, рассчитывающий на ещё не применённую миграцию (например,
# enum-значение 'issue_fix' в photo_target), падал 500-й на реальных
# пользователях в поле. Все миграции в проекте идемпотентны (IF NOT EXISTS),
# так что повторный прогон на каждом рестарте контейнера безопасен.
ENTRYPOINT ["./docker-entrypoint.sh"]
# CMD, не часть entrypoint — docker-entrypoint.sh запускает "$@", поэтому
# `docker compose run --rm api python bulk_invite.py ...` (или любой другой
# разовый скрипт из backend/) переопределяет именно эту команду и реально
# выполняется, а не тонет в жёстко зашитом запуске uvicorn.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--forwarded-allow-ips", "*"]
