from twilio.rest import Client
from src.config.settings import settings


async def call_init_node(state: dict) -> dict:

    try:
        client = Client(settings.TWILIO_SID, settings.TWILIO_AUTH)
        call = client.calls.create(
            url=f"{settings.PUBLIC_BASE_URL}/api/v1/voice/voice-response",
            to=state["call_to_number"],
            from_=settings.TWILIO_NUMBER,
        )
        print(f"[call_init_node] Call placed - SID: {call.sid}")
        return {**state, "call_sid": call.sid}

    except Exception as e:
        print(f"[call_init_node] Error: {e}")
        return {**state, "speech_error": str(e)}


