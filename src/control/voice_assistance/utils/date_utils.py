"""Date and time utilities for the voice assistance scheduling flow.

Provides IST-aware datetime helpers and human-readable formatting functions
used across multiple graph nodes to present slot dates and times to patients.
"""
import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")


def format_date_display(value) -> str | None:
    """Format a date value into a human-readable display string.

    Accepts a ``datetime.date`` object, an ISO date string, or any value that
    can be coerced to a string.  Returns ``None`` when *value* is ``None``.

    Args:
        value: Date to format; may be a ``date``, ISO string, or arbitrary object.

    Returns:
        Formatted string such as ``"Monday, Jan 05 2026"``, or ``None``.
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value.strftime("%A, %b %d %Y")
    try:
        return date.fromisoformat(str(value)).strftime("%A, %b %d %Y")
    except ValueError as e:
        logger.exception(
            "Failed to parse date value — falling back to raw string",
            extra={"value": str(value), "error": str(e)},
        )
        return str(value)


def format_time(t: time) -> str:
    """Format a ``time`` object as a 12-hour clock string without leading zeros.

    Args:
        t: Time to format.

    Returns:
        Formatted string such as ``"9:30 AM"``.
    """
    return t.strftime("%I:%M %p").lstrip("0")


def format_date(d: date) -> str:
    """Format a ``date`` as a long human-readable string.

    Args:
        d: Date to format.

    Returns:
        Formatted string such as ``"Monday, Jan 05 2026"``.
    """
    return d.strftime("%A, %b %d %Y")


def format_date_iso(d: date) -> str:
    """Format a date as a human-readable string followed by its ISO representation.

    Args:
        d: Date to format.

    Returns:
        String in the form ``"Monday, Jan 05 2026 -> 2026-01-05"``.
    """
    return f"{format_date(d)} -> {d.isoformat()}"


def now_ist() -> datetime:
    """Return the current date-time in IST (Asia/Kolkata)."""
    return datetime.now(tz=IST)


def today_ist() -> date:
    """Return today's date in IST."""
    return now_ist().date()


def now_time_ist() -> time:
    """Return the current wall-clock time in IST."""
    return now_ist().time()


def format_dates_only(dates: list[date], limit: int = 7) -> str:
    """Format a list of dates as a comma-separated display string.

    Args:
        dates: Dates to format.
        limit: Maximum number of dates to include (default 7).

    Returns:
        Comma-separated string of formatted dates.
    """
    return ", ".join(format_date(d) for d in dates[:limit])


def parse_date(value: str | None) -> date | None:
    """Parse an ISO date string into a ``date`` object.

    Args:
        value: ISO-formatted date string (``"YYYY-MM-DD"``), or ``None``.

    Returns:
        Parsed ``date``, or ``None`` if *value* is ``None`` or invalid.
    """
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def coerce_time(val: time | str | None) -> time | None:
    """Coerce a value to a ``time`` object if possible.

    Args:
        val: A ``time`` object, ISO time string, or ``None``.

    Returns:
        A ``time`` object, or ``None`` if *val* is ``None`` or cannot be parsed.
    """
    if val is None:
        return None
    if isinstance(val, time):
        return val
    try:
        return time.fromisoformat(str(val))
    except ValueError:
        return None