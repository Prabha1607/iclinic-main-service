import logging
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rest.dependencies import get_db
from src.core.services.appointments import (
    cancel_appointment,
    get_all_appointments_service,
    insert_appointment,
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
    appointment: AppointmentCreate, db: AsyncSession = Depends(get_db)
):
    try:
        await insert_appointment(db=db, appointment_data=appointment)
        return {"message": "Appointment created successfully"}
    except Exception as e:
        logger.error("Failed to create appointment", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to create appointment")


@router.put("/update/{appointment_id}", response_model=dict)
async def update_existing_appointment(
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
    appointment_id: int,
    cancellation_reason: str = Body(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        await cancel_appointment(
            appointment_id=appointment_id,
            cancellation_reason=cancellation_reason,
            db=db,
        )
        return {"message": "Appointment cancelled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel appointment {e}", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to cancel appointment")


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
        # Extract Bearer token from Authorization header
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
