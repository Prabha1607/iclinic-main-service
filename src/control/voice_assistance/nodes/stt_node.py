"""Speech-to-text (STT) node for the voice assistance graph.

Normalises raw speech input received from Twilio before passing it to the
query intent classifier for further processing.
"""
import logging

logger = logging.getLogger(__name__)

_EMPTY_TEXT = None

async def stt_node(state: dict) -> dict:
    """
    Captures and normalises raw speech input from Twilio.
    Always routes to query_intent_node for further processing.
    """
    user_text = state.get("speech_user_text")

    if not user_text:
        logger.info("Empty speech input — skipping STT processing")
        return {**state, "speech_user_text": _EMPTY_TEXT}

    cleaned = " ".join(user_text.split()).strip()
    logger.info(f"STT captured | text='{cleaned}'")

    return {**state, "speech_user_text": cleaned}

