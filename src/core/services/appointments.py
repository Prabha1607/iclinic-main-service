import logging
from datetime import UTC, datetime
from fastapi import HTTPException
from fastapi_mail import FastMail, MessageSchema
from sqlalchemy.ext.asyncio import AsyncSession
from src.data.repositories.appointments import (
    create_appointment_repo,
    get_slot_for_update,
    mark_slot_booked,
)
from src.control.voice_assistance.config import conf
from src.data.clients.auth_client import get_full_providers
from fastapi import HTTPException, status
from src.data.models.postgres.ENUM import AppointmentStatus, SlotStatus
from src.data.repositories.appointments import (
    get_appointment_by_id,
    get_appointments,
    get_instance_by_id,
)
from src.data.repositories.generic_crud import update_instance
from src.schemas.appointments import (
    AppointmentResponse,
    AppointmentTypeResponse,
    ProviderProfileResponse,
    ProviderResponse,
)

logger = logging.getLogger(__name__)


async def send_booking_confirmation_email(to_email: str, body: str) -> None:
    message = MessageSchema(
        subject="Your Appointment is Confirmed",
        recipients=[to_email],
        body=body,
        subtype="plain",
    )
    fm = FastMail(conf)
    await fm.send_message(message)
    logger.info("Booking confirmation email sent", extra={"to_email": to_email})


async def send_cancel_cancellation_email(to_email: str, body: str) -> None:
    message = MessageSchema(
        subject="Your Appointment has been Cancelled",
        recipients=[to_email],
        body=body,
        subtype="plain",
    )
    fm = FastMail(conf)
    await fm.send_message(message)
    logger.info("Cancellation email sent", extra={"to_email": to_email})


def build_cancellation_email_body(
    patient_name: str,
    appointment_type: str,
    date: str,
    start_time: str,
    end_time: str,
    reason: str,
) -> str:
    lines = [
        f"Dear {patient_name},",
        "",
        "Your appointment has been successfully cancelled.",
        "",
        f"  Appointment Type : {appointment_type}",
        f"  Date             : {date}",
        f"  Time             : {start_time} to {end_time}",
    ]

    if reason and reason != "Not specified":
        lines.append(f"  Reason           : {reason}")

    lines += [
        "",
        "If this was a mistake or you wish to rebook, please contact us.",
        "",
        "Best regards,",
        "The Appointments Team",
    ]

    return "\n".join(lines)


def build_booking_email_body(
    doctor_name: str,
    slot_display: str,
    reason: str,
    instructions: str,
    patient_name: str,
) -> str:
    lines = [
        f"Dear {patient_name},",
        "",
        "Your appointment has been successfully booked.",
        "",
        f"  Doctor  : {doctor_name}",
        f"  Slot    : {slot_display}",
    ]

    if reason:
        lines.append(f"  Reason  : {reason}")
    if instructions:
        lines.append(f"  Instructions : {instructions}")

    lines += [
        "",
        "Please arrive 10 minutes before your scheduled time.",
        "If you need to cancel, contact us as soon as possible.",
        "",
        "Best regards,",
        "The Appointments Team",
    ]

    return "\n".join(lines)

async def insert_appointment_service(
    db: AsyncSession,
    appointment_data,
):
    logger.info(
        "Inserting appointment",
        extra={
            "user_id": appointment_data.user_id,
            "provider_id": appointment_data.provider_id,
            "slot_id": appointment_data.availability_slot_id,
        },
    )

    try:
        slot = await get_slot_for_update(
            db, appointment_data.availability_slot_id
        )

        if not slot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Slot not found",
            )

        if slot.status == SlotStatus.BOOKED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slot already booked",
            )

        appointment = await create_appointment_repo(
            db=db,
            appointment_data=appointment_data,
        )

        await mark_slot_booked(db, slot)

        await db.commit()

        await db.refresh(appointment)

        logger.info(
            "Appointment created successfully",
            extra={
                "appointment_id": appointment.id,
                "slot_id": slot.id,
            },
        )

        return appointment

    except HTTPException:
        await db.rollback()
        raise

    except Exception:
        await db.rollback()

        logger.exception(
            "Failed to insert appointment",
            extra={
                "user_id": appointment_data.user_id,
                "provider_id": appointment_data.provider_id,
            },
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create appointment",
        )
    
async def update_appointment(
    appointment_id: int, db: AsyncSession, update_data
) -> None:
    logger.info("Updating appointment", extra={"appointment_id": appointment_id})
    try:
        appointment = await get_instance_by_id(id=appointment_id, db=db)

        if not appointment:
            logger.warning("Appointment not found for update", extra={"appointment_id": appointment_id})
            raise HTTPException(status_code=404, detail="Appointment not found")

        await update_instance(
            id=appointment_id,
            model=Appointment,
            db=db,
            **update_data.model_dump(exclude_unset=True),
        )
        logger.info("Appointment updated successfully", extra={"appointment_id": appointment_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to update appointment",
            extra={"appointment_id": appointment_id, "error": str(e)},
        )
        raise


async def cancel_appointment(
    appointment_id: int, cancellation_reason: str, db: AsyncSession
) -> None:
    logger.info("Cancelling appointment", extra={"appointment_id": appointment_id})
    try:
        appointment = await get_instance_by_id(id=appointment_id, db=db)

        if not appointment:
            logger.warning("Appointment not found for cancellation", extra={"appointment_id": appointment_id})
            raise HTTPException(status_code=404, detail="Appointment not found")

        if appointment.status == AppointmentStatus.CANCELLED:
            logger.warning(
                "Appointment already cancelled — skipping",
                extra={"appointment_id": appointment_id},
            )
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
        logger.info("Appointment cancelled successfully", extra={"appointment_id": appointment_id})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to cancel appointment",
            extra={"appointment_id": appointment_id, "error": str(e)},
        )
        raise


async def get_appointment_by_id_service(
    db: AsyncSession,
    appointment_id: int,
) -> dict | None:
    logger.info("Fetching appointment by ID", extra={"appointment_id": appointment_id})

    appt = await get_appointment_by_id(db=db, appointment_id=appointment_id)

    if not appt:
        logger.warning("Appointment not found", extra={"appointment_id": appointment_id})
        return None

    logger.info("Appointment fetched successfully", extra={"appointment_id": appointment_id})
    return {
        "patient_name": appt.patient_name,
        "appointment_type": (
            appt.appointment_type.name if appt.appointment_type else None
        ),
        "date": str(appt.scheduled_date),
        "start_time": str(appt.scheduled_start_time),
        "end_time": str(appt.scheduled_end_time),
        "reason": appt.reason_for_visit,
        "user_id": appt.user_id,
    }


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
    logger.info(
        "Fetching appointments",
        extra={
            "page": page,
            "page_size": page_size,
            "status": status,
            "provider_id": provider_id,
            "user_id": user_id,
            "scheduled_date_from": str(scheduled_date_from) if scheduled_date_from else None,
            "scheduled_date_to": str(scheduled_date_to) if scheduled_date_to else None,
            "is_active": is_active,
        },
    )

    try:
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
    except Exception as e:
        logger.error("Failed to fetch appointments from repository", extra={"error": str(e)})
        raise

    try:
        providers = await get_full_providers(token)
    except Exception as e:
        logger.error("Failed to fetch providers from auth client", extra={"error": str(e)})
        raise

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

        result.append(
            AppointmentResponse(
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
        )

    logger.info(
        "Appointments fetched and mapped successfully",
        extra={"count": len(result), "page": page},
    )
    return result