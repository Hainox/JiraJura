"""Checklist items admin router — CRUD для пунктов чек-листа. Список
шаблонов для прохождения обхода остаётся в sites.py (/sites/templates/checklist,
уже используется фронтендом инспектора), здесь — только редактирование."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import ChecklistItem, ChecklistTemplate, User
from app.schemas import ChecklistItemOut, ChecklistItemCreate, ChecklistItemUpdate, ChecklistTemplateOut
from app.services.permissions import require_role
from app.services.audit import log_action

router = APIRouter()


@router.get("/templates", response_model=list[ChecklistTemplateOut])
async def list_templates_admin(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Как /sites/templates/checklist, но включает отключённые (is_active=False)
    пункты — чтобы админ мог их снова включить, а не только скрыть навсегда."""
    q = select(ChecklistTemplate).options(selectinload(ChecklistTemplate.items))
    templates = (await db.execute(q)).scalars().all()
    return [
        ChecklistTemplateOut(
            id=t.id, name=t.name, site_type=t.site_type,
            items=[ChecklistItemOut.model_validate(i) for i in sorted(t.items, key=lambda x: x.sort_order)],
        )
        for t in templates
    ]


@router.post("/items", response_model=ChecklistItemOut)
async def create_checklist_item(
    data: ChecklistItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    tmpl = (await db.execute(
        select(ChecklistTemplate).where(ChecklistTemplate.id == data.template_id)
    )).scalar_one_or_none()
    if not tmpl:
        raise HTTPException(404, "Шаблон чек-листа не найден")

    item = ChecklistItem(
        template_id=data.template_id, category=data.category, question=data.question,
        sort_order=data.sort_order, is_critical=data.is_critical, requires_photo=data.requires_photo,
    )
    db.add(item)
    await db.flush()
    await log_action(db, str(current_user.id), "checklist_item_create", "checklist_item", str(item.id), {
        "template_id": str(data.template_id), "question": data.question,
    })
    await db.commit()
    await db.refresh(item)
    return ChecklistItemOut.model_validate(item)


@router.patch("/items/{item_id}", response_model=ChecklistItemOut)
async def update_checklist_item(
    item_id: str,
    data: ChecklistItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    item = (await db.execute(select(ChecklistItem).where(ChecklistItem.id == item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Пункт чек-листа не найден")

    for field in ("category", "question", "sort_order", "is_critical", "requires_photo", "is_active"):
        value = getattr(data, field)
        if value is not None:
            setattr(item, field, value)

    await log_action(db, str(current_user.id), "checklist_item_update", "checklist_item", item_id,
                      data.model_dump(exclude_unset=True))
    await db.commit()
    await db.refresh(item)
    return ChecklistItemOut.model_validate(item)


@router.delete("/items/{item_id}", response_model=ChecklistItemOut)
async def delete_checklist_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    """Мягкое удаление (is_active=False) — не хард-delete: у прошедших
    обходов уже есть ответы (checklist_answers), ссылающиеся на пункт."""
    item = (await db.execute(select(ChecklistItem).where(ChecklistItem.id == item_id))).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Пункт чек-листа не найден")
    item.is_active = False
    await log_action(db, str(current_user.id), "checklist_item_delete", "checklist_item", item_id, None)
    await db.commit()
    await db.refresh(item)
    return ChecklistItemOut.model_validate(item)
