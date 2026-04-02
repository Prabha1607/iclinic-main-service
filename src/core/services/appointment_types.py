import logging
from src.data.models.postgres.appointment_type import AppointmentType
from src.data.repositories.generic_crud import bulk_get_instance
from src.data.repositories.appointment_types import create, update_by_id
from src.schemas.appointment_types import (
    AppointmentTypeCreate,
    AppointmentTypeResponse,
    AppointmentTypeUpdate
)

logger = logging.getLogger(__name__)


async def get_appointment_types(db) -> list[AppointmentTypeResponse]:
    try:
        appointment_types = await bulk_get_instance(model=AppointmentType, db=db, is_active=True)
        logger.info(
            "Appointment types fetched successfully",
            extra={"count": len(appointment_types)},
        )
        return [AppointmentTypeResponse.model_validate(at) for at in appointment_types]
    except Exception as e:
        logger.error("Failed to fetch appointment types", extra={"error": str(e)})
        raise


async def create_appointment_type_service(
    db,
    payload: AppointmentTypeCreate,
) -> AppointmentTypeResponse:
    data = payload.model_dump()

    if not data.get("duration_minutes"):
        data["duration_minutes"] = 30

    appointment_type = await create(db, data)

    return AppointmentTypeResponse.model_validate(appointment_type)


async def update_appointment_type_service(
    db,
    appointment_type_id: int,
    payload: AppointmentTypeUpdate,
) -> AppointmentTypeResponse | None:
    data = payload.model_dump(exclude_unset=True)

    if not data:
        raise ValueError("No fields provided for update")

    appointment_type = await update_by_id(db, appointment_type_id, data)

    if appointment_type is None:
        return None

    return AppointmentTypeResponse.model_validate(appointment_type)