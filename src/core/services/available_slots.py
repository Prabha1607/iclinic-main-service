from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import SlotStatus
from src.data.repositories.available_slots import get_provider_slots_repo
from src.data.repositories.generic_crud import update_instance


async def get_provider_slots_service(db: AsyncSession, provider_id: int):
    return await get_provider_slots_repo(db=db, provider_id=provider_id)


async def change_slot_status(db: AsyncSession, slot_id: int, new_status: SlotStatus):
    await update_instance(id=slot_id, model=AvailableSlot, db=db, status=new_status)
