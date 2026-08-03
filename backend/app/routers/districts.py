"""Districts router."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import District
from app.schemas import DistrictOut

router = APIRouter()


@router.get("/", response_model=list[DistrictOut])
async def list_districts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(District).order_by(District.name))
    return [DistrictOut.model_validate(d) for d in result.scalars().all()]
