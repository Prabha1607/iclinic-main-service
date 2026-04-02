import enum


class AppointmentStatus(enum.Enum):
    SCHEDULED = "SCHEDULED"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class BookingChannel(enum.Enum):
    APP = "APP"
    CALL = "CALL"
    WALK_IN = "WALK_IN"
    VOICE = "VOICE"
    WEB = "WEB"


class SlotStatus(enum.Enum):
    AVAILABLE = "AVAILABLE"
    BOOKED = "BOOKED"
    BLOCKED = "BLOCKED"
