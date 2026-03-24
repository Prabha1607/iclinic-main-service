import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import SlotStatus
from src.data.repositories.available_slots import (
    create_slots_for_provider,
    get_provider_slots_repo,
    get_slots_by_provider,
)
from src.data.repositories.generic_crud import update_instance
from src.schemas.available_slots import (
    AvailableSlotBulkCreate,
    AvailableSlotBulkResponse,
    AvailableSlotResponse,
)

logger = logging.getLogger(__name__)


async def change_slot_status(
    db: AsyncSession, slot_id: int, new_status: SlotStatus
) -> None:
    logger.info(
        "Changing slot status",
        extra={"slot_id": slot_id, "new_status": new_status},
    )
    try:
        await update_instance(id=slot_id, model=AvailableSlot, db=db, status=new_status)
        logger.info(
            "Slot status updated successfully",
            extra={"slot_id": slot_id, "new_status": new_status},
        )
    except Exception as e:
        logger.error(
            "Failed to update slot status",
            extra={"slot_id": slot_id, "new_status": new_status, "error": str(e)},
        )
        raise


async def get_provider_slots_service(
    db: AsyncSession, provider_id: int
) -> list[AvailableSlotResponse]:
    logger.info("Fetching slots for provider", extra={"provider_id": provider_id})
    try:
        slots = await get_slots_by_provider(db=db, provider_id=provider_id)
        logger.info(
            "Provider slots fetched successfully",
            extra={"provider_id": provider_id, "count": len(slots)},
        )
        return slots
    except Exception as e:
        logger.error(
            "Failed to fetch slots for provider",
            extra={"provider_id": provider_id, "error": str(e)},
        )
        raise


async def create_provider_slots_service(
    db: AsyncSession,
    provider_id: int,
    payload: AvailableSlotBulkCreate,
    created_by: int,
) -> AvailableSlotBulkResponse:
    logger.info(
        "Creating slots for provider",
        extra={
            "provider_id": provider_id,
            "created_by": created_by,
            "slot_count": len(payload.slots) if payload.slots else 0,
        },
    )

    if not payload.slots:
        logger.warning(
            "Slot creation rejected — empty payload",
            extra={"provider_id": provider_id, "created_by": created_by},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one slot must be provided.",
        )

    try:
        inserted, skipped = await create_slots_for_provider(
            db=db,
            provider_id=provider_id,
            slots=payload.slots,
            created_by=created_by,
        )
    except Exception as e:
        logger.error(
            "Failed to create slots for provider",
            extra={"provider_id": provider_id, "created_by": created_by, "error": str(e)},
        )
        raise

    logger.info(
        "Slot creation completed",
        extra={
            "provider_id": provider_id,
            "created_by": created_by,
            "inserted": len(inserted),
            "skipped": skipped,
        },
    )

    return AvailableSlotBulkResponse(
        created=[AvailableSlotResponse.model_validate(s) for s in inserted],
        skipped=skipped,
    )

