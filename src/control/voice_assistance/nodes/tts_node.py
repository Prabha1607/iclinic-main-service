async def tts_node(state: dict) -> dict:
    print("[tts_node] -----------------------------")

    ai_text: str | None = state.get("speech_ai_text")
    print("TTS received:", state.get("speech_ai_text"))
    if not ai_text or not ai_text.strip():

        FALLBACK_TEXT = "I'm sorry, something went wrong. Please hold while I transfer you."
        ai_text = FALLBACK_TEXT

    ai_text = ai_text.replace("*", "").replace("#", "").strip()

    return {**state, "speech_ai_text": ai_text}

