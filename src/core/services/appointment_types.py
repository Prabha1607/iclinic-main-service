import logging
from sqlalchemy.ext.asyncio import AsyncSession
from src.data.models.postgres.appointment_type import AppointmentType
from src.data.repositories.generic_crud import bulk_get_instance
from sqlalchemy.ext.asyncio import AsyncSession
from src.data.repositories.appointment_types import create, update_by_id
from src.schemas.appointment_types import AppointmentTypeCreate, AppointmentTypeUpdate

logger = logging.getLogger(__name__)


async def get_appointment_types(db: AsyncSession) -> list[AppointmentType]:

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



async def create_appointment_type_service(
    db: AsyncSession,
    payload: AppointmentTypeCreate
):
    data = payload.model_dump()

    if not data.get("duration_minutes"):
        data["duration_minutes"] = 30

    appointment_type = await create(db, data)

    return appointment_type

async def update_appointment_type_service(
    db: AsyncSession,
    appointment_type_id: int,
    payload: AppointmentTypeUpdate,
):
    data = payload.model_dump(exclude_unset=True)
 
    if not data:
        raise ValueError("No fields provided for update")
 
    appointment_type = await update_by_id(db, appointment_type_id, data)
 
    if appointment_type is None:
        return None
 
    return appointment_type