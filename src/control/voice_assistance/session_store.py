import json
import logging

from sqlalchemy import text

from src.data.clients.postgres_client import AsyncSessionLocal

logger = logging.getLogger(__name__)

_SESSION_TTL_SECONDS = 30 * 60
_table_ensured = False


async def ensure_table() -> None:
    global _table_ensured
    if _table_ensured:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS call_sessions (
                call_sid   VARCHAR(64) PRIMARY KEY,
                state      TEXT        NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL
            )
        """))
        await db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_call_sessions_expires
                ON call_sessions (expires_at)
        """))
        await db.commit()
    _table_ensured = True
    logger.info("[session_store] call_sessions table ensured")


async def get_session(call_sid: str) -> dict | None:
    await ensure_table()
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("""
                    SELECT state FROM call_sessions
                    WHERE call_sid = :call_sid AND expires_at > NOW()
                """),
                {"call_sid": call_sid},
            )
            row = result.fetchone()
        if row is None:
            return None
        return json.loads(row[0])
    except Exception as e:
        logger.error("[session_store] get_session error: %s", repr(e))
        return None


async def set_session(call_sid: str, state: dict) -> None:
    await ensure_table()
    try:
        serialized = json.dumps(state, default=str)
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("""
                    INSERT INTO call_sessions (call_sid, state, expires_at)
                    VALUES (
                        :call_sid,
                        :state,
                        NOW() + make_interval(secs => :ttl)
                    )
                    ON CONFLICT (call_sid) DO UPDATE
                        SET state      = EXCLUDED.state,
                            expires_at = EXCLUDED.expires_at
                """),
                {"call_sid": call_sid, "state": serialized, "ttl": _SESSION_TTL_SECONDS},
            )
            await db.commit()
        logger.debug("[session_store] Saved session for %s", call_sid)
    except Exception as e:
        logger.error("[session_store] set_session error: %s", repr(e))

async def delete_session(call_sid: str) -> None:
    await ensure_table()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("DELETE FROM call_sessions WHERE call_sid = :call_sid"),
                {"call_sid": call_sid},
            )
            await db.commit()
        logger.info("[session_store] Deleted session for %s", call_sid)
    except Exception as e:
        logger.error("[session_store] delete_session error: %s", repr(e))


async def purge_expired() -> int:
    await ensure_table()
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("DELETE FROM call_sessions WHERE expires_at <= NOW()")
            )
            await db.commit()
            count = result.rowcount
        if count:
            logger.info("[session_store] Purged %d expired sessions", count)
        return count
    except Exception as e:
        logger.error("[session_store] purge_expired error: %s", repr(e))
        return 0
    

