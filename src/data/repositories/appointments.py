from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.ENUM import AppointmentStatus


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
):
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

    return result.scalars().all()


async def get_instance_by_id(db: AsyncSession, id: int):
    stmt = select(Appointment).where(Appointment.id == id)

    result = await db.execute(stmt)

    return result.scalar_one_or_none()
