import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


def format_date_display(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.strftime("%A, %b %d %Y")
    try:
        return date.fromisoformat(str(value)).strftime("%A, %b %d %Y")
    except Exception as e:
        logger.warning(
            "Failed to parse date value — falling back to raw string",
            extra={"value": str(value), "error": str(e)},
        )
        return str(value)


def format_time(t: time) -> str:
    return t.strftime("%I:%M %p").lstrip("0")


def format_date(d: date) -> str:
    return d.strftime("%A, %b %d %Y")


def format_date_iso(d: date) -> str:
    return f"{format_date(d)} -> {d.isoformat()}"


def now_ist() -> datetime:
    return datetime.now(tz=IST)


def today_ist() -> date:
    return now_ist().date()


def now_time_ist() -> time:
    return now_ist().time()


def format_dates_only(dates: list[date], limit: int = 7) -> str:
    return ", ".join(format_date(d) for d in dates[:limit])


def parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except Exception:
        return None


def coerce_time(val: time | str | None) -> time | None:
    if val is None:
        return None
    if isinstance(val, time):
        return val
    try:
        return time.fromisoformat(str(val))
    except Exception:
        return None