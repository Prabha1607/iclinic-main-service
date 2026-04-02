from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.rest.dependencies import get_current_user, get_db
from src.core.services.available_slots import (
    create_provider_slots_service,
    get_provider_slots_service,
)
from src.schemas.available_slots import (
    AvailableSlotBulkCreate,
    AvailableSlotBulkResponse,
    AvailableSlotResponse,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/slots", tags=["Slots"])

@router.get("/providers/{provider_id}", response_model=list[AvailableSlotResponse])
async def get_provider_slots(
    provider_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve all available slots for a given provider.

    Fetches every open appointment slot currently associated with the specified
    provider from the database. Returns an empty list when the provider exists
    but has no slots configured.

    Args:
        provider_id: Primary key of the provider whose slots are being queried.
        db:          Async database session injected by ``get_db``.

    Returns:
        list[AvailableSlotResponse]: Ordered list of available slot records.
        Returns an empty list when no slots are found.

    Raises:
        HTTPException 404: When the provider does not exist (raised by the service layer).
        HTTPException 500: When an unexpected error occurs during slot retrieval.
    """
    logger.info("Fetching slots for provider_id=%d", provider_id)
    try:
        slots = await get_provider_slots_service(db=db, provider_id=provider_id)
        logger.info(
            "Successfully fetched %d slot(s) for provider_id=%d",
            len(slots),
            provider_id,
        )
        return slots
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Unexpected error while fetching slots for provider_id=%d", provider_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving provider slots.",
        )


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
    """
    Bulk-create available appointment slots for a given provider.

    Accepts a list of slot definitions and persists them against the specified
    provider in a single operation. The authenticated user's ID is recorded as
    the creator of every slot in the batch.

    Args:
        provider_id:  Primary key of the provider the slots are being created for.
        payload:      Bulk-create payload containing a list of slot definitions.
        db:           Async database session injected by ``get_db``.
        current_user: Authenticated user payload injected by ``get_current_user``.
                      The ``id`` field is used to populate ``created_by`` on each slot.

    Returns:
        AvailableSlotBulkResponse: Summary of the bulk-create operation, including
        the newly created slot records.

    Raises:
        HTTPException 404: When the provider does not exist (raised by the service layer).
        HTTPException 422: When the payload fails business-rule validation
                           (e.g. overlapping slots, slots in the past).
        HTTPException 500: When an unexpected error occurs during slot creation.
    """
    created_by = current_user["id"]
    logger.info(
        "Creating slots for provider_id=%d by user_id=%s (slot_count=%d)",
        provider_id,
        created_by,
        len(payload.slots) if hasattr(payload, "slots") else "unknown",
    )
    try:
        result = await create_provider_slots_service(
            db=db,
            provider_id=provider_id,
            payload=payload,
            created_by=created_by,
        )
        logger.info(
            "Successfully created slots for provider_id=%d by user_id=%s",
            provider_id,
            created_by,
        )
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning(
            "Validation error creating slots for provider_id=%d by user_id=%s: %s",
            provider_id,
            created_by,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception:
        logger.exception(
            "Unexpected error creating slots for provider_id=%d by user_id=%s",
            provider_id,
            created_by,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating provider slots.",
        )