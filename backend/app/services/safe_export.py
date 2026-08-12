"""Защита от записи персональных данных в backend/uploads/ — та
смонтирована в docker-compose.prod.yml и раздаётся наружу БЕЗ авторизации
через /uploads/... (см. app/main.py: app.mount("/uploads", StaticFiles(...))).
CSV с ФИО/телефонами/паролями/токенами приглашений, однажды туда
записанный, скачивается кем угодно по прямой ссылке — уже случалось на
проде (reissued*.csv, by_district/ лежали в uploads/ несколько дней).

Только os — ни SQLAlchemy, ни FastAPI, чтобы разовые скрипты в backend/
(reissue_invites.py и т.п.) могли импортировать это, не таща за собой
весь граф зависимостей приложения (та же причина, по которой они
избегают импортировать app.models — см. докстринг любого из них).
"""
import os


def reject_uploads_path(out_path: str) -> None:
    """Прервать выполнение (SystemExit), если out_path указывает внутрь
    backend/uploads/ (при запуске из /app в контейнере — просто uploads/)."""
    uploads_abs = os.path.abspath("uploads")
    if os.path.commonpath([os.path.abspath(out_path), uploads_abs]) == uploads_abs:
        raise SystemExit(
            f"--out указывает внутрь uploads/ ({out_path}) — эта папка раздаётся "
            "публично без авторизации. Используйте, например, --out /app/exports/..."
        )


def ensure_parent_dir(out_path: str) -> None:
    """mkdir -p для директории out_path, если она задана (относительный
    путь без директории — например, просто 'result.csv' — не трогаем)."""
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
