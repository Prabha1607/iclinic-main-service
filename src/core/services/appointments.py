from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.clients.auth_client import get_full_providers
from src.data.models.postgres.appointment import Appointment
from src.data.models.postgres.available_slot import AvailableSlot
from src.data.models.postgres.ENUM import AppointmentStatus, SlotStatus
from src.data.repositories.appointments import get_appointments, get_instance_by_id
from src.data.repositories.generic_crud import insert_instance, update_instance
from src.schemas.appointments import (
    AppointmentResponse,
    AppointmentTypeResponse,
    ProviderProfileResponse,
    ProviderResponse,
)


async def insert_appointment(db: AsyncSession, appointment_data):
    try:
        appointment = await insert_instance(
            model=Appointment, db=db, **appointment_data.model_dump()
        )

        stmt = (
            update(AvailableSlot)
            .where(AvailableSlot.id == appointment_data.availability_slot_id)
            .values(status=SlotStatus.BOOKED)
        )

        await db.execute(stmt)
        await db.commit()

        return appointment

    except Exception as e:
        print("CREATE APPOINTMENT ERROR:", e)
        raise


async def update_appointment(appointment_id: int, db: AsyncSession, update_data):
    try:
        appointment = await get_instance_by_id(id=appointment_id, db=db)

        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")

        await update_instance(
            id=appointment_id,
            model=Appointment,
            db=db,
            **update_data.model_dump(exclude_unset=True),
        )

    except HTTPException:
        raise
    except Exception:
        raise Exception("Failed to update appointment")


async def cancel_appointment(
    appointment_id: int, cancellation_reason: str, db: AsyncSession
):
    try:
        appointment = await get_instance_by_id(id=appointment_id, db=db)

        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")

        if appointment.status == AppointmentStatus.CANCELLED:
            return

        await update_instance(
            id=appointment_id,
            model=Appointment,
            db=db,
            status=AppointmentStatus.CANCELLED,
            cancellation_reason=cancellation_reason,
            cancelled_at=datetime.now(UTC),
            is_active=False,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise Exception(f"Failed to cancel appointment {e}")


async def get_all_appointments_service(
    db: AsyncSession,
    token: str,
    page: int,
    page_size: int,
    status=None,
    provider_id=None,
    user_id=None,
    scheduled_date_from=None,
    scheduled_date_to=None,
    is_active=None,
) -> list[AppointmentResponse]:

    appointments = await get_appointments(
        db=db,
        page=page,
        page_size=page_size,
        status=status,
        provider_id=provider_id,
        user_id=user_id,
        scheduled_date_from=scheduled_date_from,
        scheduled_date_to=scheduled_date_to,
        is_active=is_active,
    )

    # Fetch providers from Auth Service
    providers = await get_full_providers(token)

    # Convert list → fast lookup dictionary
    provider_map = {p["id"]: p for p in providers}

    result = []

    for appt in appointments:
        instructions = appt.instructions or (
            appt.appointment_type.instructions if appt.appointment_type else None
        )

        provider_data = provider_map.get(appt.provider_id)

        provider_response = None
        if provider_data:
            profile = provider_data.get("provider_profile")

            provider_response = ProviderResponse(
                id=provider_data["id"],
                first_name=provider_data["first_name"],
                last_name=provider_data["last_name"],
                email=provider_data["email"],
                phone_no=provider_data["phone_no"],
                provider_profile=(
                    ProviderProfileResponse(
                        specialization=profile["specialization"],
                        qualification=profile["qualification"],
                        experience=profile["experience"],
                        bio=profile["bio"],
                    )
                    if profile
                    else None
                ),
            )

        response = AppointmentResponse(
            id=appt.id,
            user_id=appt.user_id,
            provider_id=appt.provider_id,
            appointment_type_id=appt.appointment_type_id,
            availability_slot_id=appt.availability_slot_id,
            patient_name=appt.patient_name,
            scheduled_date=appt.scheduled_date,
            scheduled_start_time=appt.scheduled_start_time,
            scheduled_end_time=appt.scheduled_end_time,
            status=appt.status,
            reason_for_visit=appt.reason_for_visit,
            notes=appt.notes,
            booking_channel=appt.booking_channel,
            instructions=instructions,
            cancelled_at=appt.cancelled_at,
            cancellation_reason=appt.cancellation_reason,
            created_at=appt.created_at,
            updated_at=appt.updated_at,
            provider=provider_response,
            appointment_type=(
                AppointmentTypeResponse(
                    id=appt.appointment_type.id,
                    name=appt.appointment_type.name,
                    description=appt.appointment_type.description,
                    duration_minutes=appt.appointment_type.duration_minutes,
                    instructions=appt.appointment_type.instructions,
                )
                if appt.appointment_type
                else None
            ),
        )

        result.append(response)

    return result
