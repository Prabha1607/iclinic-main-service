"""HTTP client for the iClinic auth service.

Provides async helpers to retrieve users and provider lists from the
authentication micro-service via its internal REST API.
"""
import httpx
from src.config.settings import settings

AUTH_SERVICE_URL = settings.AUTH_SERVICE_URL + "/api/v1"


async def get_full_providers(token: str, appointment_type_id: int | None = None):
    """Fetch providers filtered by appointment type from the auth service.

    Returns an empty list immediately when ``appointment_type_id`` is absent
    or not an integer, avoiding unnecessary network calls.

    Args:
        token: Bearer JWT token for authorisation.
        appointment_type_id: If provided, only returns providers who offer this
            appointment type.

    Returns:
        List of provider dicts returned by the auth service, or ``[]``.
    """

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
    """Look up a user by phone number, email, or another unique identifier.

    Args:
        identifier: Phone number, email, or other identifier string.

    Returns:
        User dict from the auth service, or ``None`` if not found.

    Raises:
        Exception: If the auth service is unreachable.
    """

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
    """Fetch a single user record by numeric ID.

    Args:
        token: Bearer JWT token for authorisation.
        user_id: Numeric ID of the user to retrieve.

    Returns:
        User dict, or ``None`` if the user does not exist.

    Raises:
        Exception: If the auth service is unreachable.
    """
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
    

    