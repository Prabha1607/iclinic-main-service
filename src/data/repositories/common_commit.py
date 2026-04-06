import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def commit_transaction(db: AsyncSession) -> None:
    logger.info("Committing transaction")
    try:
        await db.commit()
        logger.info("Transaction committed successfully")
    except SQLAlchemyError as e:
        logger.exception("Transaction failed — rolling back", extra={"error": str(e)})
        await db.rollback()
        raise