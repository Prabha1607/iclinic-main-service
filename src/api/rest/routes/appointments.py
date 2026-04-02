import logging
from datetime import date
from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.rest.dependencies import get_current_user, get_db
from src.core.services.appointments import (
    build_booking_email_body,
    build_cancellation_email_body,
    cancel_appointment,
    get_all_appointments_service,
    get_appointment_by_id_service,
    insert_appointment_service,
    send_booking_confirmation_email,
    send_cancel_cancellation_email,
    update_appointment,
)
from src.data.clients.auth_client import fetch_user_by_id
from src.schemas.appointments import (
    MessageResponse,
    AppointmentCreate,
    AppointmentResponse,
    AppointmentUpdate,
    AppointmentStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/booking", tags=["Booking"])

@router.post("/create", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    request: Request,
    appointment: AppointmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Create a new appointment and dispatch a booking confirmation email.

    Validates the Authorization header, resolves both the patient and provider
    via the auth service, persists the appointment record, and sends a
    confirmation email to the patient. Email delivery failures are logged but
    do not abort the request — the appointment is still created.

    Args:
        request:      Incoming HTTP request used to extract the Authorization header.
        appointment:  Appointment creation payload containing patient, provider,
                      schedule, and visit details.
        db:           Async database session injected by ``get_db``.
        current_user: Authenticated user payload injected by ``get_current_user``.

    Returns:
        dict: ``{"message": "Appointment created successfully"}`` on success.

    Raises:
        HTTPException 400: When the Authorization header is absent or the slot
                           is already booked.
        HTTPException 401: When the Authorization header is malformed or the
                           scheme is not Bearer.
        HTTPException 404: When the patient, provider, or slot cannot be resolved.
        HTTPException 500: When an unexpected error occurs during appointment
                           creation or database persistence.
    """
    logger.info(
        "Create appointment requested",
        extra={"user_id": appointment.user_id, "provider_id": appointment.provider_id},
    )

    credential = request.headers.get("Authorization")
    if not credential:
        logger.warning("Missing Authorization header on create-appointment request")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Bearer authorization required"},
        )

    scheme, _, token = credential.partition(" ")
    if scheme.lower() != "bearer" or not token:
        logger.warning("Malformed Authorization header on create-appointment request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format",
        )

    try:
        user = await fetch_user_by_id(token=token, user_id=appointment.user_id)
        provider = await fetch_user_by_id(token=token, user_id=appointment.provider_id)
    except Exception as e:
        logger.error("Failed to resolve user or provider", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create appointment",
        )

    if not user:
        logger.warning("User not found", extra={"user_id": appointment.user_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not provider:
        logger.warning("Provider not found", extra={"provider_id": appointment.provider_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    try:
        email_body = build_booking_email_body(
            doctor_name=f"{provider['first_name']} {provider['last_name']}",
            patient_name=appointment.patient_name,
            slot_display=appointment.scheduled_date,
            reason=appointment.reason_for_visit,
            instructions=appointment.instructions,
        )

        await insert_appointment_service(db=db, appointment_data=appointment)
        logger.info(
            "Appointment persisted successfully",
            extra={"user_id": appointment.user_id, "provider_id": appointment.provider_id},
        )
    except LookupError as e:
        logger.warning("Slot not found during appointment creation", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        logger.warning("Slot already booked during appointment creation", extra={"error": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Failed to persist appointment", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create appointment",
        )

    try:
        await send_booking_confirmation_email(user["email"], body=email_body)
        logger.info("Booking confirmation email sent", extra={"email": user["email"]})
    except Exception as e:
        logger.error(
            "Booking confirmation email failed — appointment still created",
            extra={"email": user["email"], "error": str(e)},
        )

    return MessageResponse(message="Appointment created successfully")


@router.put("/update/{appointment_id}", response_model=MessageResponse)
async def update_existing_appointment(
    appointment_id: int,
    appointment_update: AppointmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing appointment by its ID.

    Applies the supplied partial update payload to the appointment record
    identified by ``appointment_id``. Only fields present in the payload
    are modified; omitted fields retain their current values.

    Args:
        appointment_id:     Primary key of the appointment to update.
        appointment_update: Partial update payload with the fields to modify.
        db:                 Async database session injected by ``get_db``.

    Returns:
        dict: ``{"message": "Appointment updated successfully"}`` on success.

    Raises:
        HTTPException 404: When no appointment with the given ID exists.
        HTTPException 500: When an unexpected error occurs during the update.
    """
    logger.info("Update appointment requested", extra={"appointment_id": appointment_id})
    try:
        await update_appointment(
            appointment_id=appointment_id,
            db=db,
            update_data=appointment_update,
        )
        logger.info("Appointment updated successfully", extra={"appointment_id": appointment_id})
        return MessageResponse(message="Appointment updated successfully")
    except LookupError as e:
        logger.warning("Appointment not found for update", extra={"appointment_id": appointment_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            "Failed to update appointment",
            extra={"appointment_id": appointment_id, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update appointment",
        )


@router.patch("/cancel/{appointment_id}", response_model=MessageResponse)
async def cancel_existing_appointment(
    request: Request,
    appointment_id: int,
    cancellation_reason: str = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Cancel an appointment and dispatch a cancellation notification email.

    Looks up the appointment, validates the Authorization header, resolves the
    patient via the auth service, marks the appointment as cancelled with the
    supplied reason, and sends a cancellation email to the patient. Email
    delivery failures are logged but do not roll back the cancellation.

    Args:
        request:             Incoming HTTP request used to extract the Authorization header.
        appointment_id:      Primary key of the appointment to cancel.
        cancellation_reason: Plain-text reason for the cancellation supplied in
                             the request body.
        db:                  Async database session injected by ``get_db``.

    Returns:
        dict: ``{"message": "Appointment cancelled successfully"}`` on success.

    Raises:
        HTTPException 400: When the Authorization header is absent.
        HTTPException 401: When the Authorization header is malformed or the
                           scheme is not Bearer.
        HTTPException 404: When no appointment with the given ID exists, or when
                           the associated patient cannot be resolved via the
                           auth service.
        HTTPException 500: When an unexpected error occurs during cancellation
                           or database persistence.
    """
    logger.info("Cancel appointment requested", extra={"appointment_id": appointment_id})

    try:
        appointment = await get_appointment_by_id_service(db=db, appointment_id=appointment_id)
    except Exception as e:
        logger.error(
            "Failed to fetch appointment for cancellation",
            extra={"appointment_id": appointment_id, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel appointment",
        )

    if not appointment:
        logger.warning("Appointment not found for cancellation", extra={"appointment_id": appointment_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    credential = request.headers.get("Authorization")
    if not credential:
        logger.warning("Missing Authorization header on cancel-appointment request")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Bearer authorization required"},
        )

    scheme, _, token = credential.partition(" ")
    if scheme.lower() != "bearer" or not token:
        logger.warning("Malformed Authorization header on cancel-appointment request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format",
        )

    try:
        user = await fetch_user_by_id(token=token, user_id=appointment["user_id"])
    except Exception as e:
        logger.error(
            "Failed to resolve user for cancellation email",
            extra={"user_id": appointment["user_id"], "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel appointment",
        )

    if not user:
        logger.warning("User not found for cancellation", extra={"user_id": appointment["user_id"]})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    try:
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
        logger.info("Appointment cancelled successfully", extra={"appointment_id": appointment_id})
    except LookupError as e:
        logger.warning("Appointment not found for cancellation", extra={"appointment_id": appointment_id})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            "Failed to persist appointment cancellation",
            extra={"appointment_id": appointment_id, "error": str(e)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel appointment",
        )

    try:
        await send_cancel_cancellation_email(user["email"], body=email_body)
        logger.info("Cancellation email sent", extra={"email": user["email"]})
    except Exception as e:
        logger.error(
            "Cancellation email failed — appointment still cancelled",
            extra={"email": user["email"], "error": str(e)},
        )

    return MessageResponse(message="Appointment cancelled successfully")


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
    """
    Retrieve a paginated, filtered list of appointments.

    Supports optional filtering by appointment status, provider, patient,
    scheduled date range, and active state. All filters are combinable;
    omitting a filter returns results regardless of that field's value.

    Args:
        request:              Incoming HTTP request used to extract the Bearer token
                              passed through to downstream service calls.
        page:                 1-based page number (default: ``1``).
        page_size:            Maximum number of records per page (default: ``10``).
        status:               Optional filter by appointment status enum value.
        provider_id:          Optional filter to return only appointments for a
                              specific provider.
        user_id:              Optional filter to return only appointments for a
                              specific patient.
        scheduled_date_from:  Optional inclusive lower bound on the scheduled date.
        scheduled_date_to:    Optional inclusive upper bound on the scheduled date.
        is_active:            Optional filter by the appointment's active flag.
        db:                   Async database session injected by ``get_db``.

    Returns:
        list[AppointmentResponse]: Paginated list of appointment records matching
        the applied filters. Returns an empty list when no records are found.

    Raises:
        HTTPException 500: When an unexpected error occurs during appointment
                           retrieval.
    """
    logger.info(
        "Fetch appointments requested",
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

    credential = request.headers.get("Authorization", "")
    token = credential.removeprefix("Bearer ").strip()

    try:
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
        logger.info(
            "Appointments fetched successfully",
            extra={"count": len(appointments), "page": page},
        )
        return appointments
    except Exception as e:
        logger.error("Failed to fetch appointments", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch appointments",
        )