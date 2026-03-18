import logging
from datetime import date
import traceback
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.data.clients.auth_client import fetch_user_by_id
from src.api.rest.dependencies import get_current_user, get_db
from src.core.services.appointments import (
    build_booking_email_body,
    build_cancellation_email_body,
    cancel_appointment,
    get_all_appointments_service,
    get_appointment_by_id_service,
    insert_appointment,
    send_booking_confirmation_email,
    send_cancel_cancellation_email,
    update_appointment,
)
from src.data.models.postgres.ENUM import AppointmentStatus
from src.schemas.appointments import (
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/booking", tags=["Booking"])


@router.post("/create", response_model=dict)
async def create_appointment(
    request: Request,
    appointment: AppointmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        user_id = appointment.user_id
        provider_id = appointment.provider_id

        credential = request.headers.get("Authorization")
        if not credential:
            return JSONResponse(
                status_code=400,
                content={"detail": "Bearer authorization required"},
            )

        scheme, _, token = credential.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Invalid authorization format")

        user = await fetch_user_by_id(token=token, user_id=user_id)
        provider = await fetch_user_by_id(token=token, user_id=provider_id)

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        doctor_name = provider["first_name"] + " " + provider["last_name"]

        patient_name = appointment.patient_name
        slot_display = appointment.scheduled_date
        reason = appointment.reason_for_visit
        instructions = appointment.instructions

        email_body = build_booking_email_body(
            doctor_name=doctor_name,
            patient_name=patient_name,
            slot_display=slot_display,
            reason=reason,
            instructions=instructions,
        )

        await insert_appointment(db=db, appointment_data=appointment)

        try:
            await send_booking_confirmation_email(user["email"], body=email_body)
        except Exception as email_error:
            logger.error(f"Email failed: {str(email_error)}")

        return {"message": "Appointment created successfully"}

    except Exception as e:
        logger.error(f"ERROR: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to create appointment")

@router.put("/update/{appointment_id}", response_model=dict)
async def update_existing_appointment(
    request : Request,
    appointment_id: int,
    appointment_update: AppointmentUpdate,
    db: AsyncSession = Depends(get_db),

):
    try:
        await update_appointment(
            appointment_id=appointment_id, db=db, update_data=appointment_update
        )
        return {"message": "Appointment updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update appointment", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to update appointment")


@router.patch("/cancel/{appointment_id}", response_model=dict)
async def cancel_existing_appointment(
    request: Request,
    appointment_id: int,
    cancellation_reason: str = Body(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        appointment = await get_appointment_by_id_service(
            db=db, appointment_id=appointment_id
        )

        if not appointment:
            raise HTTPException(status_code=404, detail="Appointment not found")

        credential = request.headers.get("Authorization")
        if not credential:
            return JSONResponse(
                status_code=400,
                content={"detail": "Bearer authorization required"},
            )

        scheme, _, token = credential.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Invalid authorization format")

        user = await fetch_user_by_id(
            token=token, user_id=appointment["user_id"]
        )

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        email_body = build_cancellation_email_body(
            patient_name=appointment["patient_name"],
            appointment_type=appointment["appointment_type"],
            date=appointment["date"],
            start_time=appointment["start_time"],
            end_time=appointment["end_time"],
            reason=appointment["reason"],
        )

        await cancel_appointment(
            appointment_id=appointment_id,
            cancellation_reason=cancellation_reason,
            db=db,
        )

        try:
            await send_cancel_cancellation_email(
                user["email"], body=email_body
            )
        except Exception as email_error:
            logger.error(f"Email failed: {str(email_error)}")

        return {"message": "Appointment cancelled successfully"}

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"ERROR: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail="Failed to cancel appointment"
        )

@router.get("/list", response_model=list[AppointmentResponse])
async def get_all_appointments(
    request: Request,
    page: int = 1,
    page_size: int = 10,
    status: AppointmentStatus | None = None,
    provider_id: int | None = None,
    user_id: int | None = None,
    scheduled_date_from: date | None = None,
    scheduled_date_to: date | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        credential = request.headers.get("Authorization", "")
        token = credential.removeprefix("Bearer ").strip()

        appointments = await get_all_appointments_service(
            db=db,
            token=token,
            page=page,
            page_size=page_size,
            status=status,
            provider_id=provider_id,
            user_id=user_id,
            scheduled_date_from=scheduled_date_from,
            scheduled_date_to=scheduled_date_to,
            is_active=is_active,
        )

        return appointments

    except Exception as e:
        logger.error("Failed to fetch appointments", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to fetch appointments")
