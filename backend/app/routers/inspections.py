"""Inspections router."""
from datetime import datetime, timezone
from typing import Optional
import uuid as _uuid
import os

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.services.permissions import check_own_or_role, in_district_scope
from app.services.timezone import MSK
from app.models import (
    Inspection, Site, Courtyard, User,
    ChecklistAnswer, ChecklistItem, ChecklistTemplate, Photo, Issue,
)
from app.schemas import (
    InspectionCreate, InspectionUpdate, InspectionOut,
    InspectionListOut, ChecklistAnswerOut, SiteOut, UserOut,
    DistrictOut, CourtyardOut, PhotoOut,
    InspectionBulkAcceptRequest, InspectionBulkAcceptOut,
)
from app.services.auth import get_current_user
from app.services.audit import log_action

router = APIRouter()

# Белый список расширений фото (как в feedback.py) — защита от stored-XSS:
# uploads/ раздаётся наружу БЕЗ авторизации (app.mount("/uploads", ...) в
# main.py), Content-Type берётся по расширению, поэтому без этого любой
# авторизованный инспектор мог бы залить .html/.svg и получить исполнение
# скрипта в origin приложения у того, кто откроет ссылку напрямую.
_ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "heic", "heif", "webp", "gif"}


@router.post("/", response_model=InspectionOut)
async def create_inspection(
    data: InspectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    site = (await db.execute(
        select(Site)
        .where(Site.id == data.site_id)
        .options(
            selectinload(Site.courtyard).selectinload(Courtyard.district),
        )
    )).scalar_one_or_none()
    if not site:
        raise HTTPException(404, "Площадка не найдена")

    # Продолжаем свой же незавершённый обход этой площадки вне зависимости
    # от того, в какой день он был начат — иначе обход, вернувшийся на
    # доработку (status снова 'in_progress') несколько дней назад, не
    # находится проверкой "за сегодня" ниже, и повторное "Начать обход"
    # тихо создаёт ещё один, осиротив исходный
    own_unfinished = (await db.execute(
        select(Inspection).where(
            Inspection.site_id == data.site_id,
            Inspection.inspector_id == current_user.id,
            Inspection.status.in_(("planned", "in_progress")),
        ).order_by(Inspection.created_at.desc())
    )).scalars().first()
    if own_unfinished:
        q = select(Inspection).where(Inspection.id == own_unfinished.id).options(
            selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
            selectinload(Inspection.inspector),
            selectinload(Inspection.answers),
            selectinload(Inspection.reviewed_by_user),
        )
        own_unfinished = (await db.execute(q)).scalar_one()
        return await _inspection_to_out(own_unfinished, db)

    # Одна проверка площадки в сутки НА ИНСПЕКТОРА — чтобы у одного
    # человека не копились случайные повторные "Начать обход" по той же
    # площадке в тот же день. Изначально лимит был глобальным (кто угодно
    # один раз в день), но на реальном использовании выяснилось, что
    # маршруты инспекторов пересекаются — второй инспектор, придя на уже
    # отмеченную коллегой сегодня площадку, получал 409 и не мог начать
    # СВОЙ обход вообще. Полночь берём московскую, а не UTC — иначе
    # "сутки" физически начинались в 03:00 по Москве (00:00 UTC), и
    # вчерашние обходы с 00:00 до 03:00 МСК ошибочно не засчитывались как
    # сегодняшние.
    # ENABLE_DAILY_INSPECTION_LIMIT=false в .env — аварийно отключить эту
    # проверку без редеплоя, если она где-то мешает реальной работе.
    if settings.ENABLE_DAILY_INSPECTION_LIMIT:
        today_start = datetime.now(MSK).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        existing_today = (await db.execute(
            select(Inspection).where(
                Inspection.site_id == data.site_id,
                Inspection.inspector_id == current_user.id,
                Inspection.created_at >= today_start,
            ).order_by(Inspection.created_at.desc())
        )).scalars().first()
        if existing_today:
            raise HTTPException(409, "Вы уже проверяли эту площадку сегодня — повторный обход в этот же день не нужен")

    # подбираем шаблон чек-листа по типу площадки
    tmpl = (await db.execute(
        select(ChecklistTemplate).where(
            ChecklistTemplate.site_type == site.type, ChecklistTemplate.is_active
        )
    )).scalar_one_or_none()

    inspection = Inspection(
        site_id=data.site_id,
        inspector_id=current_user.id,
        template_id=tmpl.id if tmpl else None,
        type=data.type,
        status="in_progress",
        started_at=datetime.now(timezone.utc),
    )
    db.add(inspection)
    await db.commit()

    # Перезагружаем с eager-load для _inspection_to_out
    q = select(Inspection).where(Inspection.id == inspection.id).options(
        selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Inspection.inspector),
        selectinload(Inspection.answers),
        selectinload(Inspection.reviewed_by_user),
    )
    inspection = (await db.execute(q)).scalar_one()
    return await _inspection_to_out(inspection, db)


@router.get("/", response_model=InspectionListOut)
async def list_inspections(
    site_id: Optional[str] = Query(None),
    inspector_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    district_id: Optional[str] = Query(None),
    all_in_district: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base = select(Inspection).options(
        selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Inspection.inspector),
        selectinload(Inspection.answers),
        selectinload(Inspection.reviewed_by_user),
    ).order_by(Inspection.created_at.desc())

    if site_id:
        base = base.where(Inspection.site_id == site_id)
    if status:
        base = base.where(Inspection.status == status)

    # all_in_district=True — инспектор просит обходы всего своего района,
    # не только свои: чтобы видеть, что площадку уже обошёл коллега, и не
    # задваивать работу (жалоба из поля — карта у инспектора красилась
    # только по его собственным обходам, площадки коллег выглядели
    # нетронутыми). Без district_id у инспектора падать в "видит всё" было
    # бы слишком широко — оставляем own-only, как и раньше.
    if current_user.role == "inspector":
        if all_in_district and current_user.district_id is not None:
            pass  # район применится ниже через effective_district_id
        else:
            base = base.where(Inspection.inspector_id == current_user.id)
    elif inspector_id:
        base = base.where(Inspection.inspector_id == inspector_id)

    # Проверяющий со своим районом всегда ограничен им; иначе (округ-wide
    # проверяющий или admin) — можно явно выбрать район через district_id
    effective_district_id = district_id
    if current_user.role == "reviewer" and current_user.district_id is not None:
        effective_district_id = str(current_user.district_id)
    elif current_user.role == "inspector" and all_in_district and current_user.district_id is not None:
        effective_district_id = str(current_user.district_id)

    if effective_district_id:
        base = base.join(Site, Inspection.site_id == Site.id).join(
            Courtyard, Site.courtyard_id == Courtyard.id
        ).where(Courtyard.district_id == effective_district_id)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    q = base.offset(offset).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    # Пакетно вместо по 2 запроса на строку (см. комментарий в
    # _inspection_to_out) — иначе MapPage/MyInspectionsPage с page_size
    # 500-1000 превращаются в тысячи последовательных запросов.
    ids = [r.id for r in rows]
    issues_counts: dict = {}
    photos_by_inspection: dict = {}
    if ids:
        for insp_id, cnt in (await db.execute(
            select(Issue.inspection_id, func.count())
            .where(Issue.inspection_id.in_(ids))
            .group_by(Issue.inspection_id)
        )).all():
            issues_counts[insp_id] = cnt

        for p in (await db.execute(
            select(Photo).where(
                Photo.inspection_id.in_(ids),
                Photo.target_type.in_(["inspection", "checklist_answer"]),
            ).order_by(Photo.created_at.asc())
        )).scalars().all():
            photos_by_inspection.setdefault(p.inspection_id, []).append(p)

    items = [
        await _inspection_to_out(
            i, db,
            _issues_count=issues_counts.get(i.id, 0),
            _photos=photos_by_inspection.get(i.id, []),
        )
        for i in rows
    ]
    return InspectionListOut(total=total, items=items)


@router.post("/bulk-accept", response_model=InspectionBulkAcceptOut)
async def bulk_accept_inspections(
    data: InspectionBulkAcceptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Массово принять обходы без единого замечания и без своей проверки —
    чтобы не нажимать «Принять» по одному на каждой из сотен «зелёных»
    площадок. Список id от клиента не считается доверенным: каждый обход
    здесь перепроверяется на сервере (статус/район/уже проверен кем-то),
    те, что не проходят проверку, просто пропускаются, а не валят весь
    запрос."""
    if current_user.role != "reviewer":
        raise HTTPException(403, "Массовая приёмка — только для проверяющего")

    ids = [str(i) for i in data.ids]
    rows = (await db.execute(
        select(Inspection).where(Inspection.id.in_(ids)).options(
            selectinload(Inspection.site).selectinload(Site.courtyard),
        )
    )).scalars().all()

    issue_counts = dict((await db.execute(
        select(Issue.inspection_id, func.count())
        .where(Issue.inspection_id.in_(ids))
        .group_by(Issue.inspection_id)
    )).all())

    now = datetime.now(timezone.utc)
    accepted = 0
    skipped = len(ids) - len(rows)  # id, которых вообще не нашли в базе
    for obj in rows:
        district_id = obj.site.courtyard.district_id if obj.site and obj.site.courtyard else None
        eligible = (
            obj.status == "completed"
            and obj.reviewed_by is None
            and issue_counts.get(obj.id, 0) == 0
            and in_district_scope(current_user, district_id)
            # Самопроверка запрещена и здесь — иначе проверяющий/админ,
            # владеющий собственным "зелёным" обходом, мог бы принять его
            # одним движением в массовой приёмке.
            and str(obj.inspector_id) != str(current_user.id)
        )
        if not eligible:
            skipped += 1
            continue
        obj.reviewed_by = current_user.id
        obj.reviewed_at = now
        accepted += 1

    if accepted:
        await log_action(db, str(current_user.id), "inspection_bulk_accept", "inspection", None, {
            "accepted": accepted, "skipped": skipped,
        })
    await db.commit()
    return InspectionBulkAcceptOut(accepted=accepted, skipped=skipped)


@router.get("/{inspection_id}", response_model=InspectionOut)
async def get_inspection(
    inspection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Inspection).where(Inspection.id == inspection_id).options(
        selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Inspection.inspector),
        selectinload(Inspection.answers),
        selectinload(Inspection.reviewed_by_user),
    )
    obj = (await db.execute(q)).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Обход не найден")

    if current_user.role == "inspector" and obj.inspector_id != current_user.id:
        # Не свой обход — разрешаем только на чтение и только в своём районе
        # (посмотреть, что коллега уже сделал на площадке, не задваивая
        # работу); PATCH по-прежнему требует check_own_or_role в
        # update_inspection и этим не затрагивается.
        district_id = obj.site.courtyard.district_id if obj.site and obj.site.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Обход вне вашего района")
    elif current_user.role == "reviewer":
        district_id = obj.site.courtyard.district_id if obj.site and obj.site.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Обход вне вашего района")

    return await _inspection_to_out(obj, db)


@router.patch("/{inspection_id}", response_model=InspectionOut)
async def update_inspection(
    inspection_id: str,
    data: InspectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = (await db.execute(
        select(Inspection).where(Inspection.id == inspection_id).options(
            selectinload(Inspection.site).selectinload(Site.courtyard),
        )
    )).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Обход не найден")
    check_own_or_role(current_user, obj.inspector_id, "reviewer", "admin")
    if current_user.role == "reviewer":
        district_id = obj.site.courtyard.district_id if obj.site and obj.site.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Обход вне вашего района")

    is_owner = str(current_user.id) == str(obj.inspector_id)

    existing_issues_count = (await db.execute(
        select(func.count()).select_from(Issue).where(Issue.inspection_id == obj.id)
    )).scalar_one() or 0
    is_green_before_update = obj.status == "completed" and existing_issues_count == 0
    if (
        current_user.role == "admin"
        and data.status is not None
        and not is_owner
        and is_green_before_update
    ):
        raise HTTPException(403, "Зелёные обходы принимает проверяющий")

    # Обход уже проверен (reviewed_by проставлен) — владелец больше не может
    # задним числом поменять ответы чек-листа или статус, иначе отметка
    # "проверено" перестаёт что-либо гарантировать (проверяющий одобрил один
    # контент, а в базе задним числом оказывается другой). Правки после
    # проверки — только через официальный цикл "вернуть на доработку", тот
    # сбрасывает reviewed_by ниже и снова открывает запись для правок.
    if obj.reviewed_by is not None and is_owner and (data.answers is not None or data.status is not None):
        raise HTTPException(
            409,
            "Обход уже проверен — менять чек-лист или статус после проверки нельзя. "
            "Дождитесь возврата на доработку от проверяющего.",
        )

    # Возврат на доработку без комментария бессмысленен для инспектора —
    # тот же гейт, что уже есть для замечаний (issues.py, revision_needed).
    if (data.status == "in_progress" and current_user.role in ("reviewer", "admin")
            and not (data.reviewer_comment or "").strip()):
        raise HTTPException(400, "Укажите комментарий — что нужно доработать")

    if data.status:
        # Фото общего вида площадки обязательно при завершении обхода самим
        # инспектором — это чек-листовый пункт "Общий вид / Фото общего
        # вида площадки" (requires_photo=TRUE), проверяется чуть ниже вместе
        # с остальными requires_photo-пунктами (missing_photo_items). Раньше
        # тут же стояла ОТДЕЛЬНАЯ проверка на фото с target_type='inspection'
        # (кнопка "Добавить общее фото" в шапке) — тот же смысл, но другая
        # загрузка, и инспекторы, приложившие фото к чек-листовому пункту,
        # но не воспользовавшиеся отдельной кнопкой, не могли завершить
        # обход с непонятной причины. Обе кнопки закрывали один и тот же
        # пункт чек-листа для человека, поэтому дублирующий гейт убран —
        # достаточно одного requires_photo-пункта.
        obj.status = data.status
        if data.status in ("completed", "issues_found", "critical"):
            obj.completed_at = datetime.now(timezone.utc)
    if data.comment is not None:
        obj.comment = data.comment
    # Только reviewer/admin — иначе владелец-инспектор (check_own_or_role
    # выше пускает и его) мог бы сам стереть/подделать комментарий
    # проверяющего, например скрыть, что обход вернули на доработку.
    if data.reviewer_comment is not None and current_user.role in ("reviewer", "admin"):
        obj.reviewer_comment = data.reviewer_comment
    if data.gps_lat is not None:
        obj.gps_lat = data.gps_lat
    if data.gps_lon is not None:
        obj.gps_lon = data.gps_lon

    # Если reviewer/admin меняет статус — фиксируем кто и когда проверил.
    # Два исключения:
    #  - status == "in_progress" (возврат на доработку) — это тоже решение
    #    проверяющего, но не финальное одобрение: снимаем "проверено",
    #    чтобы пересданный обход снова считался непроверенным и не висел
    #    с чужим "✓ Проверен" поверх ещё не осмотренного контента.
    #  - is_owner (проверяющий/админ проверяет СВОЙ ЖЕ обход — например,
    #    был повышен из инспектора и открыл старую запись) — самопроверка
    #    запрещена: отметка "проверено" не проставляется, обход остаётся
    #    в очереди для реального стороннего проверяющего.
    if current_user.role in ("reviewer", "admin") and data.status:
        if data.status == "in_progress":
            obj.reviewed_by = None
            obj.reviewed_at = None
        elif not is_owner:
            obj.reviewed_by = current_user.id
            obj.reviewed_at = datetime.now(timezone.utc)
        await log_action(db, str(current_user.id), "inspection_review", "inspection", inspection_id, {
            "status": data.status, "reviewer_comment": data.reviewer_comment,
        })

    if data.answers:
        answer_by_item: dict[str, ChecklistAnswer] = {}
        for ans in data.answers:
            item_id = str(ans.checklist_item_id)
            existing = (await db.execute(
                select(ChecklistAnswer).where(
                    ChecklistAnswer.inspection_id == inspection_id,
                    ChecklistAnswer.checklist_item_id == item_id,
                )
            )).scalar_one_or_none()
            if existing:
                existing.result = ans.result
                existing.comment = ans.comment
                answer_by_item[item_id] = existing
            else:
                new_answer = ChecklistAnswer(
                    inspection_id=inspection_id,
                    checklist_item_id=item_id,
                    result=ans.result,
                    comment=ans.comment,
                )
                db.add(new_answer)
                answer_by_item[item_id] = new_answer

        # Автосоздание замечания по каждому пункту, отмеченному "Не ОК" —
        # раньше это был отдельный необязательный ручной шаг («Создать
        # замечание»), и множество реальных дефектов из чек-листа никогда
        # не попадали дальше в работу/отчётность (см. аудит статистики
        # районов — «Замечаний создано» массово расходилось с фактическим
        # числом найденных нарушений). Теперь дефект в чек-листе всегда
        # порождает отслеживаемое замечание без лишних действий инспектора;
        # кнопка «Создать замечание» остаётся для наблюдений вне чек-листа.
        # UNIQUE-индекс на checklist_answer_id (см. миграцию d1e2f3a4b5c6)
        # и проверка ниже не дают задвоить замечание при повторном
        # сохранении/редактировании того же ответа.
        defect_item_ids = [iid for iid, a in answer_by_item.items() if a.result == "defect"]
        if defect_item_ids:
            await db.flush()  # проставляет .id новым ChecklistAnswer

            defect_answer_ids = [answer_by_item[iid].id for iid in defect_item_ids]
            items_by_id = {
                str(i.id): i for i in (await db.execute(
                    select(ChecklistItem).where(ChecklistItem.id.in_(defect_item_ids))
                )).scalars().all()
            }
            already_issued = {
                str(row) for row in (await db.execute(
                    select(Issue.checklist_answer_id).where(Issue.checklist_answer_id.in_(defect_answer_ids))
                )).scalars().all()
            }
            for item_id in defect_item_ids:
                answer = answer_by_item[item_id]
                if str(answer.id) in already_issued:
                    continue
                item = items_by_id.get(item_id)
                if not item:
                    continue
                db.add(Issue(
                    inspection_id=inspection_id,
                    site_id=obj.site_id,
                    checklist_answer_id=answer.id,
                    category_id=item.category_id,
                    title=item.question,
                    description=answer.comment,
                    criticality="high" if item.is_critical else "medium",
                    status="open",
                    created_by=current_user.id,
                ))

    # Пункты чек-листа с requires_photo=TRUE (например «Фото общего вида
    # площадки») были помечены как обязательные к фото ещё в schema.sql, но
    # это никогда не проверялось — обход можно было завершить вообще без
    # этих фото. Проверяем после апсерта ответов выше (autoflush делает
    # только что добавленные/обновлённые ChecklistAnswer видимыми для
    # запроса ниже) и, как и общее фото площадки, только когда статус
    # меняет сам владелец-инспектор.
    if (data.status in ("completed", "issues_found", "critical")
            and str(obj.inspector_id) == str(current_user.id)):
        missing_photo_items = (await db.execute(
            select(ChecklistItem.question)
            .join(ChecklistAnswer, ChecklistAnswer.checklist_item_id == ChecklistItem.id)
            .outerjoin(Photo, Photo.checklist_answer_id == ChecklistAnswer.id)
            .where(
                ChecklistAnswer.inspection_id == inspection_id,
                ChecklistItem.requires_photo.is_(True),
                Photo.id.is_(None),
            )
        )).scalars().all()
        if missing_photo_items:
            raise HTTPException(400, f"Нужно фото для пункта(ов) чек-листа: {', '.join(missing_photo_items)}")

    await db.commit()

    # Перезагружаем с eager-load для _inspection_to_out (db.refresh не подтягивает
    # связи, а обращение к ним лениво вне greenlet-контекста async-сессии падает
    # с MissingGreenlet)
    q = select(Inspection).where(Inspection.id == obj.id).options(
        selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Inspection.inspector),
        selectinload(Inspection.answers),
        selectinload(Inspection.reviewed_by_user),
    )
    obj = (await db.execute(q)).scalar_one()
    return await _inspection_to_out(obj, db)


UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")

@router.post("/{inspection_id}/photos", response_model=PhotoOut)
async def upload_inspection_photo(
    inspection_id: str,
    file: UploadFile = File(...),
    gps_lat: Optional[float] = Query(None),
    gps_lon: Optional[float] = Query(None),
    taken_at: Optional[datetime] = Query(None),
    checklist_answer_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Загрузить фото для обхода или конкретного пункта чек-листа."""
    obj = (await db.execute(
        select(Inspection).where(Inspection.id == inspection_id).options(
            selectinload(Inspection.site).selectinload(Site.courtyard),
        )
    )).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Обход не найден")

    # Проверяем права
    check_own_or_role(current_user, obj.inspector_id, "reviewer", "admin")
    if current_user.role == "reviewer":
        district_id = obj.site.courtyard.district_id if obj.site and obj.site.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Обход вне вашего района")

    target_type = "checklist_answer" if checklist_answer_id else "inspection"

    # Сохраняем файл (потоково, с проверкой размера — file.size ненадёжен,
    # если клиент не прислал Content-Length)
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else ""
    if ext and ext not in _ALLOWED_PHOTO_EXTENSIONS:
        raise HTTPException(400, f"Недопустимый тип файла: .{ext}")
    safe_ext = ext or "jpg"
    filename = f"{_uuid.uuid4()}.{safe_ext}"
    rel_path = os.path.join("inspections", filename)
    abs_path = os.path.join(UPLOAD_DIR, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    max_bytes = settings.MAX_PHOTO_SIZE_MB * 1024 * 1024
    size = 0
    with open(abs_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                f.close()
                os.remove(abs_path)
                raise HTTPException(413, f"Файл больше {settings.MAX_PHOTO_SIZE_MB} МБ")
            f.write(chunk)

    photo = Photo(
        target_type=target_type,
        inspection_id=obj.id,
        checklist_answer_id=checklist_answer_id if checklist_answer_id else None,
        storage_path=rel_path,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        taken_at=taken_at,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return _photo_to_out(photo)


@router.get("/{inspection_id}/photos", response_model=list[PhotoOut])
async def list_inspection_photos(
    inspection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = (await db.execute(
        select(Inspection).where(Inspection.id == inspection_id).options(
            selectinload(Inspection.site).selectinload(Site.courtyard),
        )
    )).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Обход не найден")
    if current_user.role == "inspector":
        check_own_or_role(current_user, obj.inspector_id, "reviewer", "admin")
    elif current_user.role == "reviewer":
        district_id = obj.site.courtyard.district_id if obj.site and obj.site.courtyard else None
        if not in_district_scope(current_user, district_id):
            raise HTTPException(403, "Обход вне вашего района")

    q = select(Photo).where(
        Photo.inspection_id == inspection_id,
        Photo.target_type.in_(["inspection", "checklist_answer"]),
    ).order_by(Photo.created_at.asc())
    rows = (await db.execute(q)).scalars().all()
    return [_photo_to_out(p) for p in rows]


async def _inspection_to_out(
    i: Inspection, db: AsyncSession,
    _issues_count: Optional[int] = None, _photos: Optional[list] = None,
) -> InspectionOut:
    # _issues_count/_photos — предзагруженные значения для списков (см.
    # list_inspections): без них список из page_size=1000 (карта грузит
    # именно столько на каждого инспектора/район) делал бы 2 доп. запроса
    # НА КАЖДУЮ строку — до ~2000 последовательных запросов на один заход
    # на карту. Одиночные вызовы (get/create/update одного обхода) как и
    # раньше считают на месте.
    if _issues_count is not None:
        issues_count = _issues_count
    else:
        issues_count = (await db.execute(
            select(func.count()).select_from(Issue).where(Issue.inspection_id == i.id)
        )).scalar_one() or 0

    if _photos is not None:
        photos = _photos
    else:
        photos_q = select(Photo).where(
            Photo.inspection_id == i.id,
            Photo.target_type.in_(["inspection", "checklist_answer"]),
        ).order_by(Photo.created_at.asc())
        photos = (await db.execute(photos_q)).scalars().all()

    reviewer = UserOut.model_validate(i.reviewed_by_user) if i.reviewed_by_user else None

    return InspectionOut(
        id=i.id,
        site_id=i.site_id,
        inspector=UserOut.model_validate(i.inspector),
        type=i.type,
        status=i.status,
        started_at=i.started_at,
        completed_at=i.completed_at,
        gps_lat=i.gps_lat,
        gps_lon=i.gps_lon,
        comment=i.comment,
        reviewer_comment=i.reviewer_comment,
        reviewed_by=reviewer,
        reviewed_at=i.reviewed_at,
        created_at=i.created_at,
        site=SiteOut(
            id=i.site.id, type=i.site.type, area_m2=i.site.area_m2,
            courtyard=CourtyardOut.model_validate(i.site.courtyard),
            district=DistrictOut.model_validate(i.site.courtyard.district),
            is_active=i.site.is_active,
            lat=None, lon=None,  # инспекции не вычисляют геометрию
        ),
        answers=[ChecklistAnswerOut.model_validate(a) for a in (i.answers or [])],
        issues_count=issues_count,
        is_green=i.status == "completed" and issues_count == 0,
        photos_count=len(photos),
        photos=[_photo_to_out(p) for p in photos],
    )


def _photo_to_out(p: Photo) -> PhotoOut:
    return PhotoOut(
        id=p.id,
        target_type=p.target_type,
        inspection_id=p.inspection_id,
        issue_id=p.issue_id,
        checklist_answer_id=p.checklist_answer_id,
        url=f"/uploads/{p.storage_path}",
        thumbnail_url=f"/uploads/{p.thumbnail_path}" if p.thumbnail_path else None,
        gps_lat=p.gps_lat,
        gps_lon=p.gps_lon,
        taken_at=p.taken_at,
        created_at=p.created_at,
    )
