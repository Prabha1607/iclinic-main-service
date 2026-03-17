import json
import logging
import sys
import time

from fastapi import Request
from fastapi.responses import Response
from pythonjsonlogger import jsonlogger


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    logger.handlers.clear()

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)

    # File Handler
    file_handler = logging.FileHandler("app.log")
    json_formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(message)s "
        "%(url)s %(method)s %(process_time)s %(status_code)s "
        "%(request_body)s %(response_body)s"
    )
    file_handler.setFormatter(json_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


logger = logging.getLogger(__name__)


_SKIP_BODY_PATHS = {"/api/v1/voice/audio", "/health", "/metrics"}


def _try_parse_json(raw: str) -> str | dict:
    """Return parsed dict if valid JSON, else return raw string."""
    try:
        return json.loads(raw)
    except Exception:
        return raw


async def logging_middleware(request: Request, call_next):
    start = time.time()
    path = request.url.path

    request_body = None
    if path not in _SKIP_BODY_PATHS:
        try:
            raw = await request.body()
            request_body = _try_parse_json(raw.decode("utf-8"))
        except Exception:
            request_body = "<unreadable>"

    logger.info(
        "Incoming request",
        extra={
            "url": path,
            "method": request.method,
            "request_body": request_body,
            "status_code": None,
            "process_time": None,
            "response_body": None,
        },
    )

    response = await call_next(request)
    process_time = round(time.time() - start, 4)

    response_body = None
    if path not in _SKIP_BODY_PATHS:
        try:
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            raw_response = b"".join(chunks)
            response_body = _try_parse_json(raw_response.decode("utf-8"))

            response = Response(
                content=raw_response,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        except Exception:
            response_body = "<unreadable>"

    logger.info(
        "Request processed",
        extra={
            "url": path,
            "method": request.method,
            "process_time": process_time,
            "status_code": response.status_code,
            "request_body": None,
            "response_body": response_body,
        },
    )

    return response
