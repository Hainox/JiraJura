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

  # перевыпустить ссылки только по одному району (например, если после
  # рассылки выяснилось, что именно в этом районе ссылки уже не работают —
  # 72 часа с исходной выдачи истекли раньше, чем их успели раздать людям):
  docker compose -f docker-compose.prod.yml exec api python reissue_invites.py --district "Левобережный" --apply --out /app/uploads/reissued_levoberezhny.csv
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


async def main(apply: bool, out_path: str, district: str | None):
    engine = create_async_engine(DATABASE_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        query = (
            "SELECT ui.id, ui.login, ui.full_name, ui.role, ui.district_id, "
            "ui.expires_at, d.name AS district_name "
            "FROM user_invites ui LEFT JOIN districts d ON d.id = ui.district_id "
            "WHERE ui.used_at IS NULL"
        )
        params = {}
        if district:
            # ILIKE — совпадение без учёта регистра, чтобы не размышлять
            # над точным написанием района на вводе в консоль
            query += " AND d.name ILIKE :district"
            params["district"] = district
        query += " ORDER BY ui.full_name, ui.created_at DESC"
        rows = (await db.execute(text(query), params)).fetchall()

        if district and not rows:
            print(f"Ничего не найдено для района {district!r} — проверьте точное "
                  f"написание названия района (см. раздел «Районы» в админке).")
            await engine.dispose()
            return

        label = f" (район: {district})" if district else ""
        print(f"Приглашений без завершённой регистрации{label}: {len(rows)}\n")
        if not rows:
            await engine.dispose()
            return

        # брак: логин == ФИО или содержит кириллицу — переслать нечего
        malformed = [r for r in rows if CYRILLIC_RE.search(r.login) or r.login == r.full_name]
        clean = [r for r in rows if r not in malformed]

        # дубли по ФИО среди чистых: оставляем самую свежую запись (первая
        # после ORDER BY full_name, created_at DESC), остальные — в список
        # на ручное удаление. Дедуп по (district_id, ФИО), а не по одному
        # ФИО — иначе два РАЗНЫХ человека с одинаковым именем в разных
        # районах считались бы дублями друг друга, и один из них молча не
        # получал бы перевыпущенную ссылку вообще.
        seen_names = set()
        to_reissue = []
        duplicates = []
        for r in clean:
            key = (r.district_id, r.full_name)
            if key in seen_names:
                duplicates.append(r)
            else:
                seen_names.add(key)
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
            out_rows.append([r.login, r.full_name, r.role, r.district_name or "", link])
        await db.commit()

        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Логин", "ФИО", "Роль", "Район", "Ссылка"])
            w.writerows(out_rows)

        print(f"\n[DONE] Перевыпущено: {len(out_rows)}. Ссылки действуют {REISSUE_HOURS // 24} дней.")
        print(f"Отчёт сохранён: {out_path}")
        print("Скачайте файл с сервера, разошлите ссылки лично, затем удалите файл с сервера (ПДн).")

    await engine.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Переиздание просроченных приглашений на регистрацию")
    p.add_argument("--apply", action="store_true", help="перевыпустить токены (иначе только отчёт)")
    p.add_argument("--out", default="reissued_invites.csv", help="куда сохранить CSV со ссылками")
    p.add_argument("--district", default=None, help="перевыпустить только для одного района (по названию, без учёта регистра)")
    args = p.parse_args()
    asyncio.run(main(args.apply, args.out, args.district))
