"""
FastAPI dependency providers for the iClinic main service.

Supplies reusable dependencies for database session management and
authenticated user resolution, consumed via FastAPI's ``Depends`` mechanism.
"""
from fastapi import HTTPException, Request
import logging
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from sqlalchemy.exc import SQLAlchemyError
from src.config.jwt_handler import verify_access_token
from src.data.clients.postgres_client import AsyncSessionLocal


async def get_db() -> AsyncSession:
    """
    Provide an async SQLAlchemy session for the duration of a request.

    Yields a session from the connection pool and ensures it is closed
    after the request completes, whether or not an exception occurred.

    Yields:
        AsyncSession: An active async database session.

    Raises:
        Exception: Re-raises any exception that occurs during the request
                   after logging it to stdout.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except SQLAlchemyError as e:
            logger.exception("DB ERROR: %s", e)
            raise


async def get_current_user(request: Request) -> dict:
    """
    Resolve and validate the authenticated user from the incoming request.

    Extracts the Bearer token from the Authorization header or falls back
    to the ``access_token`` cookie. Verifies the JWT and returns the
    decoded user payload.

    Args:
        request: The incoming HTTP request used to extract the token.

    Returns:
        dict: Authenticated user data containing ``id``, ``email``,
        ``phone_number``, ``name``, and ``role_id``.

    Raises:
        HTTPException 401: When the token is missing, invalid, or expired.
        HTTPException 500: When an unexpected error occurs during
                           token verification.
    """
    try:
        credential = request.headers.get("Authorization")
        if credential:
            _, _, token = credential.partition(" ")
        else:
            token = request.cookies.get("access_token")

        if not token:
            raise HTTPException(status_code=401, detail="Access token missing")

        payload = await verify_access_token(token)
        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        return {
            "id": payload.get("id"),
            "email": payload.get("email"),
            "phone_number": payload.get("phone_number"),
            "name": payload.get("name"),
            "role_id": payload.get("role_id"),
        }

    except HTTPException:
        raise
    except RuntimeError:
        logger.exception("Authentication failed")
        raise HTTPException(status_code=500, detail="Authentication failed")