import httpx
from src.config.settings import settings

AUTH_SERVICE_URL = settings.AUTH_SERVICE_URL + "/api/v1"


async def get_full_providers(token: str, appointment_type_id: int | None = None):

    if not appointment_type_id or not isinstance(appointment_type_id, int):
        return []

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{AUTH_SERVICE_URL}/users/providers/by-type",
            params={"appointment_type_id": appointment_type_id, "is_active": True},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()


async def get_user_by_identifier(identifier: str):

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{AUTH_SERVICE_URL}/internal/users/by-identifier",
                params={"identifier": identifier},
                timeout=10.0,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except httpx.RequestError:
        raise Exception("Auth service unavailable")
    
async def fetch_user_by_id(token: str, user_id: int):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{AUTH_SERVICE_URL}/users/{user_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0
            )

            if resp.status_code == 404:
                return None  

            resp.raise_for_status()  
            return resp.json()

    except httpx.RequestError as e:
        raise Exception(f"Auth service unavailable: {e}")
    

    