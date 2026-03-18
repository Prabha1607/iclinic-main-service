from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, model_validator

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

class AvailableSlotCreate(BaseModel):
    availability_date: date
    start_time: time
    end_time: time
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_times(self) -> "AvailableSlotCreate":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class AvailableSlotBulkCreate(BaseModel):
    slots: list[AvailableSlotCreate]
    

class AvailableSlotBulkResponse(BaseModel):
    created: list[AvailableSlotResponse]
    skipped: int

    