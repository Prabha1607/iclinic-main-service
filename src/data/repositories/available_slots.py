from datetime import datetime, timezone, timedelta
from sqlalchemy import select, and_, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import SlotStatus
from src.schemas.available_slots import AvailableSlotCreate

IST = timezone(timedelta(hours=5, minutes=30))


def _today_and_now():
    now_ist = datetime.now(IST)
    return now_ist.date(), now_ist.time().replace(tzinfo=None)


async def get_provider_slots_repo(db: AsyncSession, provider_id: int):
    today, now = _today_and_now()

    stmt = select(AvailableSlot).where(
        AvailableSlot.provider_id == provider_id,
        AvailableSlot.status == SlotStatus.AVAILABLE,
        AvailableSlot.is_active == True,
        or_(
            AvailableSlot.availability_date > today,
            and_(
                AvailableSlot.availability_date == today,
                AvailableSlot.start_time > now,  
            ),
        ),
    )

    result = await db.execute(stmt)
    return result.scalars().all()


async def get_slots_by_provider(
    db: AsyncSession, provider_id: int
) -> list[AvailableSlot]:
    today, now = _today_and_now()

    result = await db.execute(
        select(AvailableSlot)
        .where(
            AvailableSlot.provider_id == provider_id,
            AvailableSlot.is_active == True,
            or_(
                AvailableSlot.availability_date > today,
                and_(
                    AvailableSlot.availability_date == today,
                    AvailableSlot.start_time > now,  
                ),
            ),
        )
        .order_by(AvailableSlot.availability_date, AvailableSlot.start_time)
    )
    return result.scalars().all()




async def create_slots_for_provider(
    db: AsyncSession,
    provider_id: int,
    slots: list[AvailableSlotCreate],
    created_by: int,
) -> tuple[list[AvailableSlot], int]:
   
    if not slots:
        return [], 0

    values = [
        {
            "provider_id": provider_id,
            "availability_date": slot.availability_date,
            "start_time": slot.start_time,
            "end_time": slot.end_time,
            "notes": slot.notes,
            "created_by": created_by,
        }
        for slot in slots
    ]

    stmt = (
        insert(AvailableSlot)
        .values(values)
        .on_conflict_do_nothing(
            constraint="unique_available_slot"
        )
        .returning(AvailableSlot)
    )

    result = await db.execute(stmt)
    await db.commit()

    inserted = result.scalars().all()
    skipped = len(slots) - len(inserted)

    return inserted, skipped