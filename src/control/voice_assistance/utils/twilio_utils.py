from twilio.twiml.voice_response import Gather, Say
from src.config.settings import settings

def say(parent, text: str) -> None:
    ssml = f'<speak><prosody rate="{settings.SPEAKING_RATE}">{text}</prosody></speak>'
    parent.append(Say(message=ssml, voice=settings.VOICE))


def make_gather() -> Gather:
    return Gather(
        input="speech",
        action="/api/v1/voice/voice-response",
        method="POST",
        speech_timeout=settings.SPEECH_TIMEOUT,
        timeout=settings.GATHER_TIMEOUT,
        action_on_empty_result=settings.ACTION_ON_EMPTY_RESULT,
        speech_model="phone_call",
        language=settings.LANGUAGE,
    )

