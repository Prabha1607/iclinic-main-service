import logging
import time
from threading import Lock

logger = logging.getLogger(__name__)

# Session TTL: 30 minutes — enough for the longest intake call
_SESSION_TTL_SECONDS = 30 * 60

_store: dict[str, dict] = {}
_lock = Lock()


# Return the stored state for a call, or None if expired / not found.
def get_session(call_sid: str) -> dict | None:
    with _lock:
        entry = _store.get(call_sid)
        if entry is None:
            return None
        if time.time() - entry["ts"] > _SESSION_TTL_SECONDS:
            logger.info("[session_store] Session expired for %s", call_sid)
            del _store[call_sid]
            return None
        return entry["state"]


# Persist the state for a call.
def set_session(call_sid: str, state: dict) -> None:

    with _lock:
        _store[call_sid] = {"state": state, "ts": time.time()}
    logger.debug("[session_store] Saved session for %s", call_sid)


# Remove a session
def delete_session(call_sid: str) -> None:
    with _lock:
        _store.pop(call_sid, None)
    logger.info("[session_store] Deleted session for %s", call_sid)


# Remove all expired sessions.
def purge_expired() -> int:
    now = time.time()
    with _lock:
        expired = [
            sid
            for sid, entry in _store.items()
            if now - entry["ts"] > _SESSION_TTL_SECONDS
        ]
        for sid in expired:
            del _store[sid]
    if expired:
        logger.info("[session_store] Purged %d expired sessions", len(expired))
    return len(expired)
