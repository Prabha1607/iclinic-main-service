from datetime import date, datetime, time

from pydantic import BaseModel

from src.data.models.postgres.ENUM import SlotStatus


class AvailableSlotResponse(BaseModel):
    id: int
    provider_id: int

    availability_date: date
    start_time: time
    end_time: time

    status: SlotStatus

    created_by: int | None = None
    notes: str | None = None

    is_active: bool

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
