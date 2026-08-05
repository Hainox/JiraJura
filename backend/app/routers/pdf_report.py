"""PDF-отчёт по одному обходу — возвращает HTML для печати."""
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Inspection, Site, Courtyard, District, ChecklistAnswer, ChecklistItem, Photo, User

router = APIRouter()

STATUS_RU = {
    "planned": "Запланирован", "in_progress": "В процессе",
    "completed": "Завершён", "issues_found": "Есть нарушения", "critical": "Критический",
}
RESULT_RU = {"ok": "В порядке", "defect": "Нарушение", "not_applicable": "Н/П", "not_checked": "Не проверено"}


@router.get("/{inspection_id}")
async def pdf_report(inspection_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    q = select(Inspection).where(Inspection.id == inspection_id).options(
        selectinload(Inspection.site).selectinload(Site.courtyard).selectinload(Courtyard.district),
        selectinload(Inspection.inspector),
        selectinload(Inspection.answers),
        selectinload(Inspection.reviewed_by_user),
    )
    insp = (await db.execute(q)).scalar_one_or_none()
    if not insp:
        raise HTTPException(404, "Обход не найден")

    # фото
    photos_q = select(Photo).where(
        Photo.inspection_id == inspection_id,
        Photo.target_type.in_(["inspection", "checklist_answer"]),
    ).order_by(Photo.created_at.asc())
    photos = (await db.execute(photos_q)).scalars().all()
    general_photos = [p for p in photos if p.target_type == "inspection"]
    defect_photos = [p for p in photos if p.target_type == "checklist_answer"]

    answers_ok = [a for a in insp.answers if a.result == "ok"]
    answers_defect = [a for a in insp.answers if a.result == "defect"]

    # items lookup
    item_ids = [a.checklist_item_id for a in insp.answers]
    items = {}
    if item_ids:
        items_q = select(ChecklistItem).where(ChecklistItem.id.in_(item_ids))
        for item in (await db.execute(items_q)).scalars().all():
            items[str(item.id)] = item

    site_str = insp.site.courtyard.name if insp.site.courtyard else "Площадка"
    district_str = insp.site.courtyard.district.name if insp.site.courtyard and insp.site.courtyard.district else ""

    # Абсолютный базовый URL для фото (чтобы работали при печати/скачивании)
    base_url = f"{request.url.scheme}://{request.url.netloc}"

    html = f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>Обход {site_str}</title>
<style>
  body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }}
  h1 {{ font-size: 20px; margin-bottom: 5px; }}
  .meta {{ color: #666; font-size: 13px; margin-bottom: 20px; }}
  .section {{ margin-bottom: 20px; }}
  .section h2 {{ font-size: 16px; border-bottom: 2px solid #2563eb; padding-bottom: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 6px 8px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
  th {{ background: #f3f4f6; font-weight: 600; }}
  .ok {{ color: #16a34a; }}
  .defect {{ color: #dc2626; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
  .badge-ok {{ background: #dcfce7; color: #16a34a; }}
  .badge-defect {{ background: #fee2e2; color: #dc2626; }}
  .photos {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .photos img {{ width: 120px; height: 90px; object-fit: cover; border-radius: 6px; border: 1px solid #e5e7eb; }}
  .footer {{ margin-top: 30px; font-size: 11px; color: #999; text-align: center; }}
  @media print {{ body {{ padding: 0; }} }}
</style></head>
<body>
<h1>Обход: {site_str}</h1>
<div class="meta">
  Район: {district_str} &bull; Тип: {insp.site.type} ({insp.site.area_m2} м²)<br>
  Инспектор: {insp.inspector.full_name} &bull;
  Дата: {insp.created_at.strftime('%d.%m.%Y %H:%M') if insp.created_at else ''} &bull;
  Статус: <strong>{STATUS_RU.get(insp.status, insp.status)}</strong>
</div>

<div class="section">
  <h2>Результаты чек-листа</h2>
  <table>
    <tr><th>Категория</th><th>Пункт</th><th>Результат</th><th>Комментарий</th></tr>
"""
    for a in answers_defect + answers_ok:
        item = items.get(str(a.checklist_item_id))
        cat = item.category if item else ""
        question = item.question if item else str(a.checklist_item_id)
        result = RESULT_RU.get(a.result, a.result)
        cls = "ok" if a.result == "ok" else "defect"
        html += f"<tr><td>{cat}</td><td>{question}</td><td class=\"{cls}\">{result}</td><td>{a.comment or ''}</td></tr>\n"

    html += "</table></div>"

    if general_photos:
        html += '<div class="section"><h2>Общие фото</h2><div class="photos">'
        for p in general_photos:
            html += f'<img src="{base_url}/uploads/{p.storage_path}" />'
        html += "</div></div>"

    if defect_photos:
        html += '<div class="section"><h2>Фото дефектов</h2><div class="photos">'
        for p in defect_photos:
            html += f'<img src="{base_url}/uploads/{p.storage_path}" />'
        html += "</div></div>"

    if insp.comment:
        html += f'<div class="section"><h2>Комментарий инспектора</h2><p>{insp.comment}</p></div>'
    if insp.reviewer_comment:
        html += f'<div class="section"><h2>Комментарий проверяющего</h2><p>{insp.reviewer_comment}</p>'
        if insp.reviewed_by_user:
            html += f'<p style="font-size:12px;color:#666">Проверил: {insp.reviewed_by_user.full_name}, {insp.reviewed_at.strftime("%d.%m.%Y") if insp.reviewed_at else ""}</p>'
        html += "</div>"

    html += f'<div class="footer">Сформировано: {insp.created_at.strftime("%d.%m.%Y") if insp.created_at else ""} &bull; Журнал обхода площадок САО</div></body></html>'

    return Response(content=html, media_type="text/html; charset=utf-8")
