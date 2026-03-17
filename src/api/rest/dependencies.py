from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.jwt_handler import verify_access_token
from src.data.clients.postgres_client import AsyncSessionLocal


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            print("DB ERROR:", e)
            raise


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Access token missing")

        payload = await verify_access_token(token)
        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        email = payload.get("email")
        phone_no = payload.get("phone_number")
        name = payload.get("name")

        return {"email": email, "phone_number": phone_no, "name": name}

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Authentication failed")
