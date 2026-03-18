from datetime import date, datetime, time

from pydantic import BaseModel, Field, field_validator

from src.data.models.postgres.ENUM import AppointmentStatus, BookingChannel

class AppointmentCreate(BaseModel):
    user_id: int
    provider_id: int
    appointment_type_id: int
    availability_slot_id: int

    patient_name: str = Field(..., min_length=1, max_length=150)

    scheduled_date: date
    scheduled_start_time: time
    scheduled_end_time: time

    reason_for_visit: str | None = None
    notes: str | None = None

    booking_channel: str | None = None 
    instructions: str | None = None

    @field_validator("scheduled_end_time")
    @classmethod
    def validate_time_order(cls, end_time, info):
        start_time = info.data.get("scheduled_start_time")
        if start_time and end_time <= start_time:
            raise ValueError("End time must be greater than start time")
        return end_time

    model_config = {"from_attributes": True}

class AppointmentUpdate(BaseModel):
    scheduled_date: date | None = None
    scheduled_start_time: time | None = None
    scheduled_end_time: time | None = None

    reason_for_visit: str | None = None
    notes: str | None = None
    instructions: str | None = None
    booking_channel: BookingChannel | None = None

    model_config = {"from_attributes": True}


class AppointmentCancel(BaseModel):
    cancellation_reason: str = Field(..., min_length=3, max_length=500)

    model_config = {"from_attributes": True}


class ProviderProfileResponse(BaseModel):
    specialization: str | None = None
    qualification: str | None = None
    experience: int | None = None
    bio: str | None = None

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    phone_no: str

    model_config = {"from_attributes": True}


class ProviderResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    phone_no: str

    provider_profile: ProviderProfileResponse | None = None

    model_config = {"from_attributes": True}


class AppointmentTypeResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    duration_minutes: int
    instructions: str | None = None

    model_config = {"from_attributes": True}


class AppointmentResponse(BaseModel):
    id: int
    user_id: int
    provider_id: int
    appointment_type_id: int
    availability_slot_id: int

    patient_name: str

    scheduled_date: date
    scheduled_start_time: time
    scheduled_end_time: time

    status: AppointmentStatus

    reason_for_visit: str | None = None
    notes: str | None = None

    booking_channel: BookingChannel | None = None
    instructions: str | None = None

    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None

    created_at: datetime
    updated_at: datetime | None = None

    user: UserResponse | None = None
    provider: ProviderResponse | None = None
    appointment_type: AppointmentTypeResponse | None = None

    model_config = {"from_attributes": True}
