from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, update

from src.data.models.postgres.appointment_type import AppointmentType


async def create(db: AsyncSession, data: dict) -> AppointmentType:
    stmt = insert(AppointmentType).values(**data).returning(AppointmentType)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()

async def update_by_id(db: AsyncSession, appointment_type_id: int, data: dict) -> AppointmentType | None:
    stmt = (
        update(AppointmentType)
        .where(AppointmentType.id == appointment_type_id)
        .values(**data)
        .returning(AppointmentType)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one_or_none()