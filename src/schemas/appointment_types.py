from datetime import datetime
from pydantic import BaseModel, Field


class AppointmentTypeCreate(BaseModel):
    name: str
    description: str | None = None
    duration_minutes: int = Field(default=30, ge=1)
    instructions: str | None = None

    model_config = {"from_attributes": True}


class AppointmentTypeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1)
    instructions: str | None = None
    is_active: bool | None = None

    model_config = {"from_attributes": True}


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


class MessageResponse(BaseModel):
    message: str

