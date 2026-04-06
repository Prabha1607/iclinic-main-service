"""Text-to-speech (TTS) node for the voice assistance graph.

Post-processes the AI response text before it is spoken aloud by Twilio,
stripping unsupported markdown characters and applying a fallback message
when no response is available.
"""
_FALLBACK_TEXT = "I'm sorry, something went wrong. Please hold while I transfer you."


async def tts_node(state: dict) -> dict:
    """Graph node that sanitises the AI response text for Twilio TTS output.

    Strips markdown symbols (``*``, ``#``) that would be read aloud verbatim,
    and substitutes a safe fallback message when ``speech_ai_text`` is absent
    or empty after stripping.

    Args:
        state: Graph state containing ``speech_ai_text`` produced by the
               previous node.

    Returns:
        Updated state with ``speech_ai_text`` set to the sanitised text.
    """
    ai_text: str = state.get("speech_ai_text") or _FALLBACK_TEXT
    ai_text = ai_text.replace("*", "").replace("#", "").strip() or _FALLBACK_TEXT
    return {**state, "speech_ai_text": ai_text}


