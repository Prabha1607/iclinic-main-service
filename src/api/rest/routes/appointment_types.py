from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.rest.dependencies import get_db
from src.core.services.appointment_types import get_appointment_types,create_appointment_type_service, update_appointment_type_service
from src.schemas.appointment_types import AppointmentTypeResponse,AppointmentTypeCreate, AppointmentTypeUpdate
import logging

router = APIRouter(prefix="/appointment-types", tags=["Appointment Types"])

logger = logging.getLogger(__name__)

@router.get("", response_model=list[AppointmentTypeResponse])
async def fetch_appointment_types(
    request : Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve all available appointment types.

    Fetches the full list of appointment type records from the database.
    This endpoint is typically used to populate selection menus during
    appointment scheduling.

    Args:
        db: Async database session injected by ``get_db``.

    Returns:
        list[AppointmentTypeResponse]: All configured appointment types.
        Returns an empty list when none are defined.

    Raises:
        HTTPException 500: When an unexpected error occurs during retrieval.
    """
    logger.info("Fetch appointment types requested")
    try:
        appointment_types = await get_appointment_types(db=db)
        logger.info(
            "Appointment types fetched successfully",
            extra={"count": len(appointment_types)},
        )
        return appointment_types
    except Exception as e:
        logger.error("Failed to fetch appointment types", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch appointment types",
        )
    
@router.post(
    "/add",
    response_model=AppointmentTypeResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_appointment_type(
    request : Request,
    payload: AppointmentTypeCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new appointment type.

    This endpoint allows creation of a new appointment type that defines
    how appointments are categorized in the system (e.g., consultation,
    follow-up, emergency).

    - If `duration_minutes` is not provided, it defaults to **30 minutes**.
    - The appointment type is marked as active by default.
    - Timestamps (`created_at`, `updated_at`) are automatically generated.

    Args:
        payload (AppointmentTypeCreate): Input data for creating the appointment type.
        db (AsyncSession): Database session dependency.

    Returns:
        AppointmentTypeResponse: The newly created appointment type.

    Raises:
        HTTPException:
            - 400 Bad Request: If validation fails or duplicate entry exists.
            - 500 Internal Server Error: If creation fails due to server issues.
    """
    try:
        logger.info("Creating appointment type", extra={"payload": payload.model_dump()})

        appointment_type = await create_appointment_type_service(
            db, payload
        )

        logger.info(
            "Appointment type created successfully",
            extra={"appointment_type_id": appointment_type.id}
        )

        return appointment_type

    except ValueError as ve:
        logger.warning(
            "Business validation failed while creating appointment type",
            extra={"error": str(ve)}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )

    except Exception as e:
        logger.exception("Unexpected error while creating appointment type")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create appointment type"
        )
    
@router.patch(
    "/{appointment_type_id}",
    response_model=AppointmentTypeResponse,
)
async def update_appointment_type(
    request : Request,
    appointment_type_id: int,
    payload: AppointmentTypeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Partially update an existing appointment type.
 
    Only the fields provided in the request body are updated; all other
    fields retain their current values (PATCH semantics).
 
    Args:
        appointment_type_id: Primary key of the appointment type to update.
        payload (AppointmentTypeUpdate): Fields to update (all optional).
        db (AsyncSession): Database session dependency.
 
    Returns:
        AppointmentTypeResponse: The updated appointment type.
 
    Raises:
        HTTPException:
            - 400 Bad Request: If the payload contains no fields.
            - 404 Not Found: If no appointment type exists for the given ID.
            - 500 Internal Server Error: If the update fails unexpectedly.
    """
    logger.info(
        "Update appointment type requested",
        extra={"appointment_type_id": appointment_type_id, "payload": payload.model_dump(exclude_unset=True)},
    )
    try:
        appointment_type = await update_appointment_type_service(
            db=db,
            appointment_type_id=appointment_type_id,
            payload=payload,
        )
 
        if appointment_type is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Appointment type {appointment_type_id} not found",
            )
 
        logger.info(
            "Appointment type updated successfully",
            extra={"appointment_type_id": appointment_type_id},
        )
        return appointment_type
 
    except HTTPException:
        raise
 
    except ValueError as ve:
        logger.warning(
            "Business validation failed while updating appointment type",
            extra={"error": str(ve)},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
 
    except Exception as e:
        logger.exception("Unexpected error while updating appointment type")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update appointment type",
        )