import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from jose import ExpiredSignatureError, JWTError, jwt

from src.config.settings import settings


async def create_access_token(payload: dict) -> dict:

    to_encode = payload.copy()
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    jti = str(uuid.uuid4())
    to_encode.update({"exp": expire, "jti": jti, "type": "access"})
    encoded_jwt = jwt.encode(
        to_encode, settings.ACCESS_SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt, jti


async def create_refresh_token(payload: dict) -> dict:

    to_encode = payload.copy()
    expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    jti = str(uuid.uuid4())
    to_encode.update({"exp": expire, "jti": jti, "type": "refresh"})
    encoded_jwt = jwt.encode(
        to_encode, settings.REFRESH_SECRET_KEY, algorithm=settings.ALGORITHM
    )
    return encoded_jwt, jti


async def verify_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, settings.ACCESS_SECRET_KEY, algorithms=[settings.ALGORITHM]
        )

        return payload
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=401, detail="Token has been expaired, please login again"
        )
    except JWTError:
        raise


async def verify_refresh_token(token: str) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Refresh token missing")
    try:
        payload = jwt.decode(
            token, settings.REFRESH_SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        return payload
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=401, detail="Token has expired, please login again"
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
