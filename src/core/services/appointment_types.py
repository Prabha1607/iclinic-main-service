"""Business logic for appointment type management.

Provides service-layer functions for fetching, creating, and updating
appointment types backed by the ``AppointmentType`` ORM model.
"""
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
    """Retrieve all active appointment types from the database.

    Args:
        db: Async SQLAlchemy session dependency.

    Returns:
        List of ``AppointmentTypeResponse`` Pydantic models.

    Raises:
        Exception: Propagates any unexpected database error after logging.
    """
    try:
        appointment_types = await bulk_get_instance(model=AppointmentType, db=db, is_active=True)
        logger.info(
            "Appointment types fetched successfully",
            extra={"count": len(appointment_types)},
        )
        return [AppointmentTypeResponse.model_validate(at) for at in appointment_types]
    except RuntimeError as e:
        logger.exception("Failed to fetch appointment types", extra={"error": str(e)})
        raise


async def create_appointment_type_service(
    db,
    payload: AppointmentTypeCreate,
) -> AppointmentTypeResponse:
    """Create a new appointment type.

    Defaults ``duration_minutes`` to 30 when not supplied in the payload.

    Args:
        db: Async SQLAlchemy session dependency.
        payload: Pydantic model containing the new appointment type data.

    Returns:
        The created ``AppointmentTypeResponse``.
    """
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
    """Update an existing appointment type by ID.

    Args:
        db: Async SQLAlchemy session dependency.
        appointment_type_id: PK of the appointment type to update.
        payload: Pydantic model containing only the fields to change.

    Returns:
        Updated ``AppointmentTypeResponse``, or ``None`` if not found.

    Raises:
        ValueError: If the payload contains no fields to update.
    """
    data = payload.model_dump(exclude_unset=True)

    if not data:
        raise ValueError("No fields provided for update")

    appointment_type = await update_by_id(db, appointment_type_id, data)

    if appointment_type is None:
        return None

    return AppointmentTypeResponse.model_validate(appointment_type)