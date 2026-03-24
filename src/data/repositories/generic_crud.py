import logging

from sqlalchemy import and_, delete, insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.data.repositories.common_commit import commit_transaction

logger = logging.getLogger(__name__)


async def insert_instance(model: type, db: AsyncSession, **kwargs) -> None:
    logger.info("Inserting record", extra={"model": model.__name__})
    try:
        stmt = insert(model).values(**kwargs)
        await db.execute(stmt)
        await commit_transaction(db=db)
        logger.info("Record inserted successfully", extra={"model": model.__name__})
    except IntegrityError as e:
        logger.error(
            "Integrity constraint violated during insert",
            extra={"model": model.__name__, "error": str(e)},
        )
        await db.rollback()
        raise
    except SQLAlchemyError as e:
        logger.error(
            "Database error during insert",
            extra={"model": model.__name__, "error": str(e)},
        )
        await db.rollback()
        raise


async def bulk_insert_instance(
    model: type, db: AsyncSession, data: list[dict]
) -> None:
    logger.info(
        "Bulk inserting records",
        extra={"model": model.__name__, "count": len(data)},
    )
    try:
        stmt = insert(model)
        await db.execute(stmt, data)
        await commit_transaction(db=db)
        logger.info(
            "Bulk insert completed successfully",
            extra={"model": model.__name__, "count": len(data)},
        )
    except SQLAlchemyError as e:
        logger.error(
            "Database error during bulk insert",
            extra={"model": model.__name__, "count": len(data), "error": str(e)},
        )
        await db.rollback()
        raise


async def update_instance(db: AsyncSession, model: type, id: int, **kwargs) -> None:
    logger.info("Updating record", extra={"model": model.__name__, "id": id})
    try:
        stmt = update(model).where(model.id == id).values(**kwargs)
        result = await db.execute(stmt)

        if result.rowcount == 0:
            logger.warning(
                "Update matched no rows — record not found",
                extra={"model": model.__name__, "id": id},
            )
            raise LookupError(f"Record not found: {model.__name__} id={id}")

        await commit_transaction(db=db)
        logger.info(
            "Record updated successfully", extra={"model": model.__name__, "id": id}
        )
    except LookupError:
        raise
    except SQLAlchemyError as e:
        logger.error(
            "Database error during update",
            extra={"model": model.__name__, "id": id, "error": str(e)},
        )
        await db.rollback()
        raise


async def bulk_update_instance(
    model: type, db: AsyncSession, filter: dict, data: dict
) -> None:
    logger.info(
        "Bulk updating records",
        extra={"model": model.__name__, "filter": filter},
    )
    try:
        stmt = update(model)

        for key, value in filter.items():
            stmt = stmt.where(getattr(model, key) == value)

        stmt = stmt.values(**data)
        result = await db.execute(stmt)

        if result.rowcount == 0:
            logger.warning(
                "Bulk update matched no rows",
                extra={"model": model.__name__, "filter": filter},
            )
            raise LookupError(f"No records found for filter: {filter}")

        await commit_transaction(db=db)
        logger.info(
            "Bulk update completed successfully",
            extra={"model": model.__name__, "rows_affected": result.rowcount},
        )
    except LookupError:
        raise
    except SQLAlchemyError as e:
        logger.error(
            "Database error during bulk update",
            extra={"model": model.__name__, "filter": filter, "error": str(e)},
        )
        await db.rollback()
        raise


async def delete_instance(id: int, model: type, db: AsyncSession) -> None:
    logger.info("Deleting record", extra={"model": model.__name__, "id": id})
    try:
        stmt = delete(model).where(model.id == id)
        result = await db.execute(stmt)

        if result.rowcount == 0:
            logger.warning(
                "Delete matched no rows — record not found",
                extra={"model": model.__name__, "id": id},
            )
            raise LookupError(f"Record not found: {model.__name__} id={id}")

        await commit_transaction(db=db)
        logger.info(
            "Record deleted successfully", extra={"model": model.__name__, "id": id}
        )
    except LookupError:
        raise
    except SQLAlchemyError as e:
        logger.error(
            "Database error during delete",
            extra={"model": model.__name__, "id": id, "error": str(e)},
        )
        await db.rollback()
        raise


async def bulk_delete_instance(
    model: type, db: AsyncSession, ids: list[int]
) -> None:
    logger.info(
        "Bulk deleting records",
        extra={"model": model.__name__, "ids": ids, "count": len(ids)},
    )
    try:
        stmt = delete(model).where(model.id.in_(ids))
        result = await db.execute(stmt)

        if result.rowcount == 0:
            logger.warning(
                "Bulk delete matched no rows",
                extra={"model": model.__name__, "ids": ids},
            )
            raise LookupError(f"No records found for ids: {ids}")

        await commit_transaction(db=db)
        logger.info(
            "Bulk delete completed successfully",
            extra={"model": model.__name__, "rows_deleted": result.rowcount},
        )
    except LookupError:
        raise
    except SQLAlchemyError as e:
        logger.error(
            "Database error during bulk delete",
            extra={"model": model.__name__, "ids": ids, "error": str(e)},
        )
        await db.rollback()
        raise


async def get_instance_by_id(
    db: AsyncSession, model: type, id: int
) -> object | None:
    logger.info("Fetching record by ID", extra={"model": model.__name__, "id": id})
    try:
        stmt = (
            select(model)
            .options(selectinload(model.patient_profile))
            .where(model.id == id)
        )
        result = await db.execute(stmt)
        instance = result.scalar_one_or_none()

        if not instance:
            logger.warning(
                "Record not found", extra={"model": model.__name__, "id": id}
            )
        else:
            logger.info(
                "Record fetched successfully", extra={"model": model.__name__, "id": id}
            )

        return instance
    except SQLAlchemyError as e:
        logger.error(
            "Database error during fetch by ID",
            extra={"model": model.__name__, "id": id, "error": str(e)},
        )
        raise


async def get_instance_by_any(
    model: type, db: AsyncSession, data: dict
) -> object | None:
    logger.info(
        "Fetching record by field match",
        extra={"model": model.__name__, "fields": list(data.keys())},
    )
    try:
        conditions = [getattr(model, key) == value for key, value in data.items()]
        stmt = select(model).where(and_(*conditions))
        result = await db.execute(stmt)
        instance = result.scalar_one_or_none()

        if not instance:
            logger.warning(
                "No record matched the given fields",
                extra={"model": model.__name__, "fields": list(data.keys())},
            )
        else:
            logger.info(
                "Record fetched successfully by field match",
                extra={"model": model.__name__},
            )

        return instance
    except SQLAlchemyError as e:
        logger.error(
            "Database error during fetch by fields",
            extra={"model": model.__name__, "error": str(e)},
        )
        raise


async def bulk_get_instance(model: type, db: AsyncSession, **kwargs) -> list:
    logger.info(
        "Bulk fetching records",
        extra={"model": model.__name__, "filters": list(kwargs.keys())},
    )
    try:
        stmt = select(model)

        for key, value in kwargs.items():
            if hasattr(model, key):
                stmt = stmt.where(getattr(model, key) == value)

        result = await db.execute(stmt)
        instances = result.scalars().all()

        logger.info(
            "Bulk fetch completed successfully",
            extra={"model": model.__name__, "count": len(instances)},
        )
        return instances
    except SQLAlchemyError as e:
        logger.error(
            "Database error during bulk fetch",
            extra={"model": model.__name__, "error": str(e)},
        )
        raise