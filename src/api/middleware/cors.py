from fastapi.middleware.cors import CORSMiddleware


def add_cors_middleware(app):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # local dev (Vite)
            "http://localhost",  # Docker nginx on :80
            "http://localhost:80",  # Docker nginx explicit port
        ],
        allow_credentials=True,
        allow_methods=["GET", "PUT", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["x-transcript", "x-response-text"],
    )
