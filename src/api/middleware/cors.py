"""
CORS middleware configuration for the iClinic REST API.

Registers the FastAPI CORSMiddleware with the allowed origins, methods,
and headers required for both local development and Cloud Run deployments.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def add_cors_middleware(app: FastAPI) -> None:
    """
    Register CORS middleware on the given FastAPI application instance.

    Allows credentialed cross-origin requests from local development servers
    and production Cloud Run frontends, with explicit method and header rules.

    Args:
        app: The FastAPI application instance to attach the middleware to.

    Returns:
        None
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            # ── Local development ──────────────────────────────────────────
            "http://localhost:5173",        # Vite dev server
            "http://localhost",             # Docker nginx on :80
            "http://localhost:80",          # Docker nginx explicit port
            "http://localhost:8080",        # API gateway local
            # ── Cloud Run ─────────────────────────────────────────────────
            "https://iclinic-api-gateway-717740758627.us-east1.run.app",
            "https://iclinic-frontend-717740758627.us-east1.run.app",
        ],
        allow_credentials=True,
        allow_methods=["GET", "PUT", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["x-transcript", "x-response-text"],
    )