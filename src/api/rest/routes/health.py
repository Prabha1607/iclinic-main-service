from sqlalchemy import text
from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.rest.dependencies import get_db

router = APIRouter()

@router.get("/health", tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    is_healthy = db_status == "healthy"

    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "version": "1.0.0",
        "services": {
            "database": db_status,
        },
    }
