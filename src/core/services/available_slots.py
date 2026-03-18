from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.repositories.available_slots import (
    get_slots_by_provider,
    create_slots_for_provider,
)
from src.schemas.available_slots import (
    AvailableSlotBulkCreate,
    AvailableSlotBulkResponse,
    AvailableSlotResponse,
)

from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import SlotStatus
from src.data.repositories.available_slots import get_provider_slots_repo
from src.data.repositories.generic_crud import update_instance



async def change_slot_status(db: AsyncSession, slot_id: int, new_status: SlotStatus):
    await update_instance(id=slot_id, model=AvailableSlot, db=db, status=new_status)


async def get_provider_slots_service(
    db: AsyncSession, provider_id: int
) -> list[AvailableSlotResponse]:
    slots = await get_slots_by_provider(db=db, provider_id=provider_id)
    return slots


async def create_provider_slots_service(
    db: AsyncSession,
    provider_id: int,
    payload: AvailableSlotBulkCreate,
    created_by: int,
) -> AvailableSlotBulkResponse:
    if not payload.slots:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one slot must be provided.",
        )

    inserted, skipped = await create_slots_for_provider(
        db=db,
        provider_id=provider_id,
        slots=payload.slots,
        created_by=created_by,
    )

    return AvailableSlotBulkResponse(
        created=[AvailableSlotResponse.model_validate(s) for s in inserted],
        skipped=skipped,
    )