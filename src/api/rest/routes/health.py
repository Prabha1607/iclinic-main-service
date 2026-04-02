"""
Health check route for the iClinic main service.

Exposes a single ``/health`` endpoint that verifies database connectivity
and returns the overall service health status.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rest.dependencies import get_db

router = APIRouter()


@router.get("/health", tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    """
    Check the health of the service and its dependencies.

    Executes a lightweight query against the database to verify connectivity
    and returns a status summary for the service and each downstream dependency.

    Args:
        db: Async database session injected by ``get_db``.

    Returns:
        dict: Health status payload containing:
            - ``status`` (str): Overall service status — ``"healthy"`` or ``"unhealthy"``.
            - ``version`` (str): Current service version string.
            - ``services`` (dict): Per-dependency status with ``"database"`` key.
    """
    try:
        await db.execute(text("SELECT 1"))
        db_status = "healthy"
    except SQLAlchemyError as e:
        db_status = f"unhealthy: {str(e)}"

    is_healthy = db_status == "healthy"

    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "version": "1.0.0",
        "services": {
            "database": db_status,
        },
    }