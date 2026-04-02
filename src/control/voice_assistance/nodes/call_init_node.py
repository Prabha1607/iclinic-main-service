"""
LangGraph node for initiating outbound Twilio calls in the iClinic voice assistance module.

Places the initial outbound call via the Twilio REST client and stores
the resulting call SID in state for use by subsequent nodes.
"""
import logging
from twilio.rest import Client
from src.config.settings import settings

logger = logging.getLogger(__name__)


async def call_init_node(state: dict) -> dict:
    """
    Initiates an outbound Twilio call as the first node in the voice flow.

    Creates a Twilio call from the configured number to the target number
    in state, pointing Twilio at the voice-response webhook. On success,
    stores the call SID in state. On failure, stores the error message so
    downstream nodes can handle it gracefully.

    Args:
        state: Graph state containing:
            - call_to_number: The recipient's phone number in E.164 format.

    Returns:
        Updated state with:
            - call_sid: Twilio call SID if the call was placed successfully.
            - speech_error: Error message string if the call failed.
    """
    try:
        client = Client(settings.TWILIO_SID, settings.TWILIO_AUTH)
        call = client.calls.create(
            url=f"{settings.PUBLIC_BASE_URL}/api/v1/voice/voice-response",
            to=state["call_to_number"],
            from_=settings.TWILIO_NUMBER,
        )
        logger.info("call_init_node: call placed", extra={"call_sid": call.sid})
        return {**state, "call_sid": call.sid}

    except RuntimeError as e:
        logger.exception("call_init_node: failed to place call", extra={"error": str(e)})
        return {**state, "speech_error": str(e)}
    