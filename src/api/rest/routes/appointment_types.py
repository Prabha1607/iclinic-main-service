import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rest.dependencies import get_db
from src.core.services.appointment_types import get_appointment_types
from src.schemas.appointment_types import AppointmentTypeResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/appointment-types", response_model=list[AppointmentTypeResponse])
async def fetch_appointment_types(
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve all available appointment types.

    Fetches the full list of appointment type records from the database.
    This endpoint is typically used to populate selection menus during
    appointment scheduling.

    Args:
        db: Async database session injected by ``get_db``.

    Returns:
        list[AppointmentTypeResponse]: All configured appointment types.
        Returns an empty list when none are defined.

    Raises:
        HTTPException 500: When an unexpected error occurs during retrieval.
    """
    logger.info("Fetch appointment types requested")
    try:
        appointment_types = await get_appointment_types(db=db)
        logger.info(
            "Appointment types fetched successfully",
            extra={"count": len(appointment_types)},
        )
        return appointment_types
    except Exception as e:
        logger.error("Failed to fetch appointment types", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch appointment types",
        )