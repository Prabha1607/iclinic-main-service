from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rest.dependencies import get_db
from src.core.services.available_slots import get_provider_slots_service
from src.schemas.available_slots import AvailableSlotResponse

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/providers/{provider_id}/slots", response_model=list[AvailableSlotResponse]
)
async def get_provider_slots(provider_id: int, db: AsyncSession = Depends(get_db)):
    slots = await get_provider_slots_service(db=db, provider_id=provider_id)
    return slots
