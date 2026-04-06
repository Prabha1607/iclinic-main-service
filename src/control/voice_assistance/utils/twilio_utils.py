"""Twilio TwiML helper utilities for the voice assistance flow.

Provides thin wrappers around Twilio TwiML <Say> and <Gather> verbs,
applying clinic-specific voice settings from the application config.
"""
from twilio.twiml.voice_response import Gather, Say
from src.config.settings import settings

def say(parent, text: str) -> None:
    """Append a <Say> TwiML verb with SSML prosody control to *parent*.

    Args:
        parent: TwiML response or verb to append to.
        text: Text to speak; wrapped in an SSML ``<prosody>`` element to
              apply the configured speaking rate and voice.
    """
    ssml = f'<speak><prosody rate="{settings.SPEAKING_RATE}">{text}</prosody></speak>'
    parent.append(Say(message=ssml, voice=settings.VOICE))


def make_gather() -> Gather:
    """Create a pre-configured Twilio <Gather> verb for speech input.

    Returns:
        A ``Gather`` verb configured to collect a speech turn, route to the
        voice-response endpoint, and apply clinic-specific timeout/model settings.
    """
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

