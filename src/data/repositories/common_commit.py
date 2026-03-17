from sqlalchemy.ext.asyncio import AsyncSession


async def commit_transaction(db: AsyncSession):
    try:
        await db.commit()

    except Exception:
        await db.rollback()
        raise
