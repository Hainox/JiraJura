# -*- coding: utf-8 -*-
"""Переиздание просроченных/недоставленных приглашений — самодостаточный,
не импортирует app.models (та же причина, что и у fix_passwords.py).

Токен приглашения нигде не хранится в открытом виде — в БД только
token_hash (sha256), сам токен отдаётся один раз в ответе API при
создании и если тогда не был скопирован/доставлен человеку — восстановить
его нельзя в принципе. Единственный способ снова дать доступ — выпустить
новый токен для того же приглашения (логин/ФИО/роль/район сохраняются).

Без --apply — только отчёт: сколько приглашений ждут регистрации, сколько
уже истекло, и что выглядит как брак/дубль и требует ручной проверки:
  - логин совпадает с ФИО (кириллица вместо нормального логина) —
    отправлять нечего, сначала логин нужно поправить вручную;
  - несколько pending-приглашений с одинаковым ФИО (обычно — разные
    варианты транслитерации логина для одного человека) — перевыпускается
    только самое свежее, остальные перечисляются отдельно для ручного
    удаления, чтобы не размножать ссылки на одного и того же сотрудника.

--apply перевыпускает токен только записям, прошедшим эти проверки, и
пишет CSV со свежими ссылками (720 часов — 30 дней, а не 72 часа: чтобы
не наступить на те же грабли ещё раз, пока ссылки физически не дойдут до
людей). ФИО и логины — персональные данные, CSV нужно скачать с сервера
и удалить, не оставлять в репозитории/переписке дольше необходимого.

Запуск на сервере:
  docker compose -f docker-compose.prod.yml exec api python reissue_invites.py
  docker compose -f docker-compose.prod.yml exec api python reissue_invites.py --apply --out /app/uploads/reissued.csv
  # скачать файл с сервера, разослать ссылки, затем удалить файл с сервера
"""
import argparse
import asyncio
import csv
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/sao_inspection")
SITE_URL = os.getenv("SITE_URL", "https://journal.yuvibot2.xyz:8443")
REISSUE_HOURS = 24 * 30  # 30 дней вместо стандартных 72 часов — только для перевыпуска
CYRILLIC_RE = re.compile(r"[а-яА-ЯёЁ]")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def main(apply: bool, out_path: str):
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        rows = (await db.execute(text(
            "SELECT id, login, full_name, role, district_id, expires_at "
            "FROM user_invites WHERE used_at IS NULL ORDER BY full_name, created_at DESC"
        ))).fetchall()

        print(f"Приглашений без завершённой регистрации: {len(rows)}\n")
        if not rows:
            await engine.dispose()
            return

        # брак: логин == ФИО или содержит кириллицу — переслать нечего
        malformed = [r for r in rows if CYRILLIC_RE.search(r.login) or r.login == r.full_name]
        clean = [r for r in rows if r not in malformed]

        # дубли по ФИО среди чистых: оставляем самую свежую запись (первая
        # после ORDER BY full_name, created_at DESC), остальные — в список
        # на ручное удаление
        seen_names = set()
        to_reissue = []
        duplicates = []
        for r in clean:
            if r.full_name in seen_names:
                duplicates.append(r)
            else:
                seen_names.add(r.full_name)
                to_reissue.append(r)

        if malformed:
            print(f"⚠ Брак — логин на кириллице/совпадает с ФИО, разослать нечего, "
                  f"нужно поправить логин вручную: {len(malformed)}")
            for r in malformed:
                print(f"   {r.login!r:35s} {r.full_name}")

        if duplicates:
            print(f"\n⚠ Дубли (несколько приглашений на одного человека, разные "
                  f"варианты логина) — оставлен только самый свежий, эти можно "
                  f"удалить вручную: {len(duplicates)}")
            for r in duplicates:
                print(f"   {r.login:25s} {r.full_name}")

        print(f"\nБудет перевыпущено ссылок: {len(to_reissue)}")

        if not apply:
            print("\nЭто был dry-run. Для перевыпуска добавьте --apply.")
            await engine.dispose()
            return

        out_rows = []
        new_expires_at = datetime.now(timezone.utc) + timedelta(hours=REISSUE_HOURS)
        for r in to_reissue:
            token = secrets.token_urlsafe(32)
            await db.execute(text(
                "UPDATE user_invites SET token_hash = :hash, expires_at = :expires_at "
                "WHERE id = :id"
            ), {"hash": _hash_token(token), "expires_at": new_expires_at, "id": r.id})
            link = f"{SITE_URL.rstrip('/')}/register/{token}"
            out_rows.append([r.login, r.full_name, r.role, link])
        await db.commit()

        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Логин", "ФИО", "Роль", "Ссылка"])
            w.writerows(out_rows)

        print(f"\n[DONE] Перевыпущено: {len(out_rows)}. Ссылки действуют {REISSUE_HOURS // 24} дней.")
        print(f"Отчёт сохранён: {out_path}")
        print("Скачайте файл с сервера, разошлите ссылки лично, затем удалите файл с сервера (ПДн).")

    await engine.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Переиздание просроченных приглашений на регистрацию")
    p.add_argument("--apply", action="store_true", help="перевыпустить токены (иначе только отчёт)")
    p.add_argument("--out", default="reissued_invites.csv", help="куда сохранить CSV со ссылками")
    args = p.parse_args()
    asyncio.run(main(args.apply, args.out))
