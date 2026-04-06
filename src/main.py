"""
Entry point for the iClinic REST API service.

Reads the PORT environment variable and starts the Uvicorn ASGI server
serving the FastAPI application defined in src.api.rest.app.
"""
import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "src.api.rest.app:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )