"""Async SQLAlchemy engine and session factory for the iClinic main service.

Exposes ``AsyncSessionLocal`` for use as a FastAPI dependency and ``Base``
as the declarative base for all ORM models.
"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base


import os

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL)
AsyncSessionLocal = async_sessionmaker(
    autoflush=False, bind=engine, class_=AsyncSession, expire_on_commit=False
)

# base class
Base = declarative_base()


async def init_db():
    """Create all ORM-mapped tables if they do not already exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
