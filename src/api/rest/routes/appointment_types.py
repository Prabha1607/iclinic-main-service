import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rest.dependencies import get_db
from src.core.services.appointment_types import get_appointment_types
from src.schemas.appointment_types import AppointmentTypeResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/appointment-types", response_model=list[AppointmentTypeResponse])
async def fetch_appointment_types(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    try:
        appointment_types = await get_appointment_types(db=db)
        return appointment_types

    except Exception as e:
        logger.error("Failed to fetch appointment types", extra={"error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to fetch appointment types")
