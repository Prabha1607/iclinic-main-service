import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from jose import ExpiredSignatureError, JWTError, jwt

from src.config.settings import settings

logger = logging.getLogger(__name__)


async def create_access_token(payload: dict) -> tuple[str, str]:
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
    except Exception as e:
        logger.error(
            "Failed to create access token",
            extra={"subject": payload.get("sub"), "error": str(e)},
        )
        raise


async def create_refresh_token(payload: dict) -> tuple[str, str]:
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
    except Exception as e:
        logger.error(
            "Failed to create refresh token",
            extra={"subject": payload.get("sub"), "error": str(e)},
        )
        raise


async def verify_access_token(token: str) -> dict:
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