from datetime import datetime

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
