from sqlalchemy import and_, delete, insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.data.repositories.common_commit import commit_transaction


async def insert_instance(model: type, db: AsyncSession, **kwargs):
    try:
        stmt = insert(model).values(**kwargs)
        await db.execute(stmt)
        await commit_transaction(db=db)

    except IntegrityError:
        await db.rollback()
        raise

    except SQLAlchemyError:
        await db.rollback()
        raise


async def bulk_insert_instance(model: type, db: AsyncSession, data: list[dict]):
    try:
        stmt = insert(model)
        await db.execute(stmt, data)
        await commit_transaction(db=db)

    except SQLAlchemyError as e:
        await db.rollback()
        raise Exception(f"Bulk insert failed: {str(e)}")


async def update_instance(db: AsyncSession, model: type, id: int, **kwargs):
    print("DB TYPE:", type(db))
    print("DEBUG DB:", db)
    print("DEBUG DB TYPE:", type(db))
    try:
        stmt = update(model).where(model.id == id).values(**kwargs)

        result = await db.execute(stmt)

        if result.rowcount == 0:
            raise Exception("Record not found")

        await commit_transaction(db=db)

    except SQLAlchemyError as e:
        await db.rollback()
        raise Exception(f"Update failed: {str(e)}")


async def Bulk_update_instance(model: type, db: AsyncSession, filter: dict, data: dict):

    try:
        stmt = update(model)

        for key, value in filter.items():
            stmt = stmt.where(getattr(model, key, value))

        stmt = stmt.values(**data)

        results = await db.execute(stmt)

        if results.rowcount == 0:
            raise Exception("Record not found")

        await commit_transaction(db=db)

    except SQLAlchemyError as e:
        await db.rollback()
        raise Exception(f"Bulk update failed: {str(e)}")


async def delete_instance(id: int, model: type, db: AsyncSession):
    try:
        stmt = delete(model).where(model.id == id)

        result = await db.execute(stmt)

        if result.rowcount == 0:
            raise Exception("Record not found")

        await commit_transaction(db=db)

    except SQLAlchemyError as e:
        await db.rollback()
        raise Exception(f"Update failed: {str(e)}")


async def bulk_delete_instance(model: type, db: AsyncSession, ids: list[int]):
    try:
        stmt = delete(model).where(model.id.in_(ids))

        result = await db.execute(stmt)

        if result.rowcount == 0:
            raise Exception("No records found to delete")

        await commit_transaction(db=db)

    except SQLAlchemyError as e:
        await db.rollback()
        raise Exception(f"Bulk delete failed: {str(e)}")


async def get_instance_by_id(db: AsyncSession, model: type, id: int):
    stmt = (
        select(model).options(selectinload(model.patient_profile)).where(model.id == id)
    )

    result = await db.execute(stmt)

    return result.scalar_one_or_none()


async def get_instance_by_any(model: type, db: AsyncSession, data: dict):
    try:
        conditions = []

        for key, value in data.items():
            column = getattr(model, key)
            conditions.append(column == value)

        stmt = select(model).where(and_(*conditions))

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    except SQLAlchemyError as e:
        raise Exception(f"Fetch failed: {str(e)}")


async def bulk_get_instance(model: type, db: AsyncSession, **kwargs):
    try:
        stmt = select(model)

        for key, value in kwargs.items():
            if hasattr(model, key):
                stmt = stmt.where(getattr(model, key) == value)

        result = await db.execute(stmt)

        return result.scalars().all()

    except SQLAlchemyError as e:
        raise Exception(f"Bulk fetch failed: {str(e)}")
