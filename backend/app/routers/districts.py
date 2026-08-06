"""Districts router."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import District, User
from app.schemas import DistrictOut
from app.services.auth import get_current_user

router = APIRouter()


@router.get("/", response_model=list[DistrictOut])
async def list_districts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(District).order_by(District.name)

    # Инспектор без района — нет доступа (неполная настройка аккаунта);
    # проверяющий без района курирует весь округ, видит все районы (как в sites.py)
    if current_user.role == "inspector":
        if current_user.district_id is not None:
            q = q.where(District.id == current_user.district_id)
        else:
            return []
    elif current_user.role == "reviewer" and current_user.district_id is not None:
        q = q.where(District.id == current_user.district_id)

    result = await db.execute(q)
    return [DistrictOut.model_validate(d) for d in result.scalars().all()]
