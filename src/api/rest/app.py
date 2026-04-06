"""
FastAPI application factory for the iClinic main service.

Configures the application lifespan, middleware stack (auth, CORS, logging),
API routers, exception handlers, and observability instrumentation
(Prometheus and OpenTelemetry).
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
import logging
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
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
from src.core.exceptions.base import AppError
from src.data.clients.postgres_client import init_db
from src.data.seeds.seed_available_slots import seed_available_slots


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage the application startup and shutdown lifecycle.

    Initialises logging on startup. Database initialisation and slot seeding
    are available but currently disabled.

    Args:
        app: The FastAPI application instance passed by the framework.

    Yields:
        None: Control is yielded back to FastAPI to serve requests.
    """
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

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """
    Handle application-level errors raised as ``AppError`` instances.

    Converts the exception into a JSON response using the status code
    and message carried by the exception.

    Args:
        request: The incoming HTTP request that triggered the error.
        exc:     The ``AppError`` instance containing status code and message.

    Returns:
        JSONResponse: Response with the exception's status code and detail message.
    """
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

Instrumentator().instrument(app).expose(app)
logger = logging.getLogger(__name__)

try:
    FastAPIInstrumentor.instrument_app(app)
except RuntimeError as e:
    logger.exception("Failed to instrument application", exc_info=True)