from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.middleware.auth import AuthorizationMiddleware
from src.api.middleware.cors import add_cors_middleware
from src.api.middleware.logging import logging_middleware, setup_logging
from src.api.rest.routes import (
    appointment_types,
    appointments,
    available_slots,
    health,
    twilio_verify,
    voice,
)
from src.data.clients.postgres_client import init_db
from src.data.seeds.seed_available_slots import seed_available_slots


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    # await init_db()
    # await seed_available_slots()
    yield


app = FastAPI(lifespan=lifespan, title="Main Service", version="1.0.0")

app.add_middleware(AuthorizationMiddleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=logging_middleware)

add_cors_middleware(app)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(router=voice.router)
api_router.include_router(router=appointments.router)
api_router.include_router(router=available_slots.router)
api_router.include_router(router=appointment_types.router)
api_router.include_router(router=twilio_verify.router)
api_router.include_router(router=health.router)

app.include_router(router=api_router)
