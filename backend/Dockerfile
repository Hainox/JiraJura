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
# пользователем на хосте): backend/uploads монтируется с хоста поверх
# /app/uploads, и на сервере его нужно один раз chown'уть под этот же UID
# (см. deploy/README.md), иначе запись новых фото будет падать с
# "Permission denied". chown всего /app — не только uploads: разовые
# эксплуатационные скрипты (bulk_invite.py и т.п., см. комментарий выше)
# тоже пишут файлы (CSV-выгрузки) в поддиректории /app.
RUN groupadd -g 10001 appgroup \
    && useradd -u 10001 -g appgroup -M -s /usr/sbin/nologin appuser \
    && chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000
# Миграции применяются автоматически на старте контейнера
# (docker-entrypoint.sh), а не отдельной ручной командой после деплоя —
# "alembic upgrade head" уже трижды забывали прогнать после git pull/build/up
# на проде, и код, рассчитывающий на ещё не применённую миграцию (например,
# enum-значение 'issue_fix' в photo_target), падал 500-й на реальных
# пользователях в поле. Все миграции в проекте идемпотентны (IF NOT EXISTS),
# так что повторный прогон на каждом рестарте контейнера безопасен.
ENTRYPOINT ["./docker-entrypoint.sh"]
