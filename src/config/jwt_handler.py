"""
JWT token creation and verification utilities for the iClinic main service.

Provides helpers to issue and validate signed access and refresh tokens
using the Jose library, with expiry, JTI, and token-type claims enforced.
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from jose import ExpiredSignatureError, JWTError, jwt

from src.config.settings import settings

logger = logging.getLogger(__name__)


async def create_access_token(payload: dict) -> tuple[str, str]:
    """
    Create a signed JWT access token from the given payload.

    Appends expiry, a unique JTI, and a ``"access"`` type claim before
    encoding with the access secret key.

    Args:
        payload: Base claims dict to encode into the token (e.g. ``sub``, ``id``).

    Returns:
        tuple[str, str]: The encoded JWT string and the generated JTI.

    Raises:
        Exception: Re-raises any error encountered during token creation.
    """
    logger.info("Creating access token", extra={"subject": payload.get("sub")})
    try:
        to_encode = payload.copy()
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        jti = str(uuid.uuid4())
        to_encode.update({"exp": expire, "jti": jti, "type": "access"})
        encoded_jwt = jwt.encode(
            to_encode, settings.ACCESS_SECRET_KEY, algorithm=settings.ALGORITHM
        )
        logger.info(
            "Access token created successfully",
            extra={"subject": payload.get("sub"), "jti": jti, "expires_at": expire.isoformat()},
        )
        return encoded_jwt, jti
    except RuntimeError as e:
        logger.exception(
            "Failed to create access token",
            extra={"subject": payload.get("sub"), "error": str(e)},
        )
        raise


async def create_refresh_token(payload: dict) -> tuple[str, str]:
    """
    Create a signed JWT refresh token from the given payload.

    Appends expiry, a unique JTI, and a ``"refresh"`` type claim before
    encoding with the refresh secret key.

    Args:
        payload: Base claims dict to encode into the token (e.g. ``sub``, ``id``).

    Returns:
        tuple[str, str]: The encoded JWT string and the generated JTI.

    Raises:
        Exception: Re-raises any error encountered during token creation.
    """
    logger.info("Creating refresh token", extra={"subject": payload.get("sub")})
    try:
        to_encode = payload.copy()
        expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        jti = str(uuid.uuid4())
        to_encode.update({"exp": expire, "jti": jti, "type": "refresh"})
        encoded_jwt = jwt.encode(
            to_encode, settings.REFRESH_SECRET_KEY, algorithm=settings.ALGORITHM
        )
        logger.info(
            "Refresh token created successfully",
            extra={"subject": payload.get("sub"), "jti": jti, "expires_at": expire.isoformat()},
        )
        return encoded_jwt, jti
    except RuntimeError as e:
        logger.exception(
            "Failed to create refresh token",
            extra={"subject": payload.get("sub"), "error": str(e)},
        )
        raise


async def verify_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.

    Args:
        token: The encoded JWT access token string to verify.

    Returns:
        dict: The decoded claims payload on successful verification.

    Raises:
        HTTPException 401: When the token has expired or is otherwise invalid.
    """
    logger.info("Verifying access token")
    try:
        payload = jwt.decode(
            token, settings.ACCESS_SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        logger.info(
            "Access token verified successfully",
            extra={"subject": payload.get("sub"), "jti": payload.get("jti")},
        )
        return payload
    except ExpiredSignatureError:
        logger.warning("Access token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired, please login again",
        )
    except JWTError as e:
        logger.warning("Access token is invalid", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


async def verify_refresh_token(token: str) -> dict:
    """
    Decode and validate a JWT refresh token.

    Args:
        token: The encoded JWT refresh token string to verify.

    Returns:
        dict: The decoded claims payload on successful verification.

    Raises:
        HTTPException 401: When the token is missing, expired, or invalid.
    """
    logger.info("Verifying refresh token")

    if not token:
        logger.warning("Refresh token is missing")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    try:
        payload = jwt.decode(
            token, settings.REFRESH_SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        logger.info(
            "Refresh token verified successfully",
            extra={"subject": payload.get("sub"), "jti": payload.get("jti")},
        )
        return payload
    except ExpiredSignatureError:
        logger.warning("Refresh token has expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired, please login again",
        )
    except JWTError as e:
        logger.warning("Refresh token is invalid", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )