import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import SlotStatus
from src.schemas.available_slots import AvailableSlotCreate

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def _today_and_now() -> tuple:
    now_ist = datetime.now(IST)
    return now_ist.date(), now_ist.time().replace(tzinfo=None)


async def get_provider_slots_repo(
    db: AsyncSession, provider_id: int
) -> list[AvailableSlot]:
    logger.info(
        "Fetching available slots for provider (repo)",
        extra={"provider_id": provider_id},
    )
    try:
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
        slots = result.scalars().all()

        logger.info(
            "Provider available slots fetched successfully",
            extra={"provider_id": provider_id, "count": len(slots)},
        )
        return slots
    except Exception as e:
        logger.error(
            "Failed to fetch available slots for provider",
            extra={"provider_id": provider_id, "error": str(e)},
        )
        raise


async def get_slots_by_provider(
    db: AsyncSession, provider_id: int
) -> list[AvailableSlot]:
    logger.info(
        "Fetching all slots for provider",
        extra={"provider_id": provider_id},
    )
    try:
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
        slots = result.scalars().all()

        logger.info(
            "Provider slots fetched successfully",
            extra={"provider_id": provider_id, "count": len(slots)},
        )
        return slots
    except Exception as e:
        logger.error(
            "Failed to fetch slots for provider",
            extra={"provider_id": provider_id, "error": str(e)},
        )
        raise


async def create_slots_for_provider(
    db: AsyncSession,
    provider_id: int,
    slots: list[AvailableSlotCreate],
    created_by: int,
) -> tuple[list[AvailableSlot], int]:
    logger.info(
        "Creating slots for provider",
        extra={
            "provider_id": provider_id,
            "created_by": created_by,
            "slot_count": len(slots),
        },
    )

    if not slots:
        logger.warning(
            "No slots provided for creation — returning empty result",
            extra={"provider_id": provider_id, "created_by": created_by},
        )
        return [], 0

    try:
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
            .on_conflict_do_nothing(constraint="unique_available_slot")
            .returning(AvailableSlot)
        )

        result = await db.execute(stmt)
        await db.commit()

        inserted = result.scalars().all()
        skipped = len(slots) - len(inserted)

        logger.info(
            "Slot creation completed",
            extra={
                "provider_id": provider_id,
                "created_by": created_by,
                "inserted": len(inserted),
                "skipped": skipped,
            },
        )
        return inserted, skipped
    except Exception as e:
        logger.error(
            "Failed to create slots for provider",
            extra={
                "provider_id": provider_id,
                "created_by": created_by,
                "slot_count": len(slots),
                "error": str(e),
            },
        )
        raise

    