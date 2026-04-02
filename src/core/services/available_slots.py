"""Business logic for provider slot management.

Provides service-layer functions for changing slot statuses, fetching
slots by provider, and bulk-creating slots with duplicate detection.
"""
from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import SlotStatus
from src.data.repositories.available_slots import (
    create_slots_for_provider,
    get_slots_by_provider,
)
from src.data.repositories.generic_crud import update_instance
from src.schemas.available_slots import (
    AvailableSlotBulkCreate,
    AvailableSlotBulkResponse,
    AvailableSlotResponse,
)
import logging


logger = logging.getLogger(__name__)


async def change_slot_status(db, slot_id: int, new_status: SlotStatus) -> None:
    """Update the status of a single availability slot.

    Args:
        db: Async SQLAlchemy session dependency.
        slot_id: PK of the slot to update.
        new_status: Target ``SlotStatus`` enum value.

    Raises:
        Exception: Propagates any database failure after logging.
    """
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
    except RuntimeError as e:
        logger.exception(
            "Failed to update slot status",
            extra={"slot_id": slot_id, "new_status": new_status, "error": str(e)},
        )
        raise


async def get_provider_slots_service(db, provider_id: int) -> list[AvailableSlotResponse]:
    """Retrieve all active slots for a given provider.

    Args:
        db: Async SQLAlchemy session dependency.
        provider_id: ID of the provider whose slots to fetch.

    Returns:
        List of ``AvailableSlotResponse`` Pydantic models.

    Raises:
        Exception: Propagates any database failure after logging.
    """
    logger.info("Fetching slots for provider", extra={"provider_id": provider_id})
    try:
        slots = await get_slots_by_provider(db=db, provider_id=provider_id)
        logger.info(
            "Provider slots fetched successfully",
            extra={"provider_id": provider_id, "count": len(slots)},
        )
        return slots
    except RuntimeError as e:
        logger.exception(
            "Failed to fetch slots for provider",
            extra={"provider_id": provider_id, "error": str(e)},
        )
        raise


async def create_provider_slots_service(
    db,
    provider_id: int,
    payload: AvailableSlotBulkCreate,
    created_by: int,
) -> AvailableSlotBulkResponse:
    """Bulk-create availability slots for a provider, skipping duplicates.

    Args:
        db: Async SQLAlchemy session dependency.
        provider_id: ID of the provider the slots belong to.
        payload: Bulk-create payload containing a list of slot definitions.
        created_by: ID of the admin user initiating the creation.

    Returns:
        ``AvailableSlotBulkResponse`` containing the created slots and a
        count of skipped duplicates.

    Raises:
        ValueError: If ``payload.slots`` is empty.
        Exception: Propagates any database failure after logging.
    """
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
        raise ValueError("At least one slot must be provided.")

    try:
        inserted, skipped = await create_slots_for_provider(
            db=db,
            provider_id=provider_id,
            slots=payload.slots,
            created_by=created_by,
        )
    except ValueError:
        raise
    except RuntimeError as e:
        logger.exception(
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

