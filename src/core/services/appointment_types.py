import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models.postgres.appointment_type import AppointmentType
from src.data.repositories.generic_crud import bulk_get_instance

logger = logging.getLogger(__name__)


async def get_appointment_types(db: AsyncSession):
    try:
        appointment_types = await bulk_get_instance(model=AppointmentType, db=db, is_active=True)
        logger.info(
            "Appointment types fetched successfully",
            extra={"count": len(appointment_types)},
        )
        return appointment_types
    except Exception as e:
        logger.error("Failed to fetch appointment types", extra={"error": str(e)})
        raise