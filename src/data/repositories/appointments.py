import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import AppointmentStatus

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models.postgres.ENUM import SlotStatus


async def create_appointment_repo(
    db: AsyncSession,
    appointment_data,
) -> Appointment:
    appointment = Appointment(**appointment_data.model_dump())

    db.add(appointment)

    await db.flush()

    return appointment


async def get_slot_for_update(
    db: AsyncSession,
    slot_id: int,
) -> AvailableSlot | None:
    stmt = (
        select(AvailableSlot)
        .where(AvailableSlot.id == slot_id)
        .with_for_update()
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def mark_slot_booked(
    db: AsyncSession,
    slot: AvailableSlot,
) -> None:
    slot.status = SlotStatus.BOOKED

async def get_appointment_by_id(
    db: AsyncSession,
    appointment_id: int,
) -> Appointment | None:
    logger.info("Fetching appointment by ID", extra={"appointment_id": appointment_id})
    try:
        stmt = (
            select(Appointment)
            .options(
                selectinload(Appointment.appointment_type),
                selectinload(Appointment.availability_slot),
            )
            .where(Appointment.id == appointment_id)
        )
        result = await db.execute(stmt)
        appointment = result.scalars().first()

        if not appointment:
            logger.warning(
                "Appointment not found", extra={"appointment_id": appointment_id}
            )
        else:
            logger.info(
                "Appointment fetched successfully",
                extra={"appointment_id": appointment_id},
            )

        return appointment
    except Exception as e:
        logger.error(
            "Failed to fetch appointment by ID",
            extra={"appointment_id": appointment_id, "error": str(e)},
        )
        raise


async def get_appointments(
    db: AsyncSession,
    page: int,
    page_size: int,
    status: AppointmentStatus | None = None,
    provider_id: int | None = None,
    user_id: int | None = None,
    scheduled_date_from: date | None = None,
    scheduled_date_to: date | None = None,
    is_active: bool | None = None,
) -> list[Appointment]:
    logger.info(
        "Fetching appointments",
        extra={
            "page": page,
            "page_size": page_size,
            "status": status,
            "provider_id": provider_id,
            "user_id": user_id,
            "scheduled_date_from": str(scheduled_date_from) if scheduled_date_from else None,
            "scheduled_date_to": str(scheduled_date_to) if scheduled_date_to else None,
            "is_active": is_active,
        },
    )
    try:
        stmt = select(Appointment).options(
            selectinload(Appointment.appointment_type),
            selectinload(Appointment.availability_slot),
        )

        if status:
            stmt = stmt.where(Appointment.status == status)
        if provider_id:
            stmt = stmt.where(Appointment.provider_id == provider_id)
        if user_id:
            stmt = stmt.where(Appointment.user_id == user_id)
        if scheduled_date_from and scheduled_date_to:
            stmt = stmt.where(
                Appointment.scheduled_date.between(scheduled_date_from, scheduled_date_to)
            )
        elif scheduled_date_from:
            stmt = stmt.where(Appointment.scheduled_date >= scheduled_date_from)
        elif scheduled_date_to:
            stmt = stmt.where(Appointment.scheduled_date <= scheduled_date_to)
        if is_active is not None:
            stmt = stmt.where(Appointment.is_active == is_active)

        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        result = await db.execute(stmt)
        appointments = result.scalars().all()

        logger.info(
            "Appointments fetched successfully",
            extra={"count": len(appointments), "page": page},
        )
        return appointments
    except Exception as e:
        logger.error(
            "Failed to fetch appointments",
            extra={
                "page": page,
                "page_size": page_size,
                "error": str(e),
            },
        )
        raise


async def get_instance_by_id(db: AsyncSession, id: int) -> Appointment | None:
    logger.info("Fetching appointment instance by ID", extra={"appointment_id": id})
    try:
        stmt = select(Appointment).where(Appointment.id == id)
        result = await db.execute(stmt)
        appointment = result.scalar_one_or_none()

        if not appointment:
            logger.warning(
                "Appointment instance not found", extra={"appointment_id": id}
            )
        else:
            logger.info(
                "Appointment instance fetched successfully",
                extra={"appointment_id": id},
            )

        return appointment
    except Exception as e:
        logger.error(
            "Failed to fetch appointment instance by ID",
            extra={"appointment_id": id, "error": str(e)},
        )
        raise

    