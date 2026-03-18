from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rest.dependencies import get_db, get_current_user
from src.core.services.available_slots import (
    get_provider_slots_service,
    create_provider_slots_service,
)
from src.schemas.available_slots import (
    AvailableSlotBulkCreate,
    AvailableSlotBulkResponse,
    AvailableSlotResponse,
)

router = APIRouter(prefix="/slots", tags=["Slots"])

@router.get("/providers/{provider_id}", response_model=list[AvailableSlotResponse])
async def get_provider_slots(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await get_provider_slots_service(db=db, provider_id=provider_id)


@router.post(
    "/providers/{provider_id}",
    response_model=AvailableSlotBulkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider_slots(
    provider_id: int,
    payload: AvailableSlotBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return await create_provider_slots_service(
        db=db,
        provider_id=provider_id,
        payload=payload,
        created_by=current_user["id"],
    )


