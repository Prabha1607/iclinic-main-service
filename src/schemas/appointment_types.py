from datetime import datetime
from pydantic import BaseModel, Field
from pydantic import BaseModel


class AppointmentTypeResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    duration_minutes: int
    instructions: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class AppointmentTypeCreate(BaseModel):
    name: str
    description: str | None = None
    duration_minutes: int = Field(default=30, ge=1)
    instructions: str | None = None

class AppointmentTypeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1)
    instructions: str | None = None
    is_active: bool | None = None