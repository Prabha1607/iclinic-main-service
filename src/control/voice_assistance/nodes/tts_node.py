_FALLBACK_TEXT = "I'm sorry, something went wrong. Please hold while I transfer you."


async def tts_node(state: dict) -> dict:
    
    ai_text: str = state.get("speech_ai_text") or _FALLBACK_TEXT
    ai_text = ai_text.replace("*", "").replace("#", "").strip() or _FALLBACK_TEXT
    return {**state, "speech_ai_text": ai_text}


