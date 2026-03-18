from typing import Any

from src.control.voice_assistance.utils import invokeLargeLLM


async def tts_node(state: dict[str, Any]) -> dict[str, Any]:
    print("[tts_node] -----------------------------")

    ai_text: str | None = state.get("speech_ai_text")
    user_text: str | None = state.get("speech_user_text")

    print("User said:", user_text)
    print("AI raw:", ai_text)

    if not ai_text or not ai_text.strip():
        ai_text = "Sorry, something went wrong. Let me help you with that."

    ai_text = ai_text.replace("*", "").replace("#", "").strip()


    def format_history(history: list[dict] | None, label: str) -> str:
        if not history:
            return ""
        lines = "\n".join(
            f"  {msg.get('role', 'user').capitalize()}: {msg.get('content', '').strip()}"
            for msg in history
            if msg.get("content", "").strip()
        )
        return f"[{label}]\n{lines}" if lines else ""

    history_blocks = [
        format_history(state.get("identity_conversation_history"), "Identity Verification"),
        format_history(state.get("clarify_conversation_history"), "Intent Clarification"),
        format_history(state.get("mapping_history"), "Symptom Mapping"),
        format_history(state.get("slot_selection_history"), "Appointment Slot Selection"),
        format_history(state.get("doctor_selection_history"), "Doctor Selection"),
    ]

    conversation_history = "\n\n".join([h for h in history_blocks if h])

    is_first_turn = not user_text or not user_text.strip()


    system_prompt = """
You are a warm, human-like voice assistant working in a healthcare call center.

Your ONLY job is to rewrite the given AI response so it sounds completely natural when spoken aloud over a phone call.

=== STRICT OUTPUT RULES ===
- Output ONLY the final spoken sentence(s). No explanations, no labels, no preamble.
- Strip all markdown, symbols, asterisks, bullet points, and formatting entirely.
- Never start with robotic openers like "Certainly!", "Of course!", "Sure!", or "Absolutely!".
- Never repeat information the user already confirmed in this conversation.
- Never add a greeting (Hello/Hi) unless the user greeted first in this turn.

=== RESPONSE LENGTH RULES ===
- For simple confirmations, questions, or status updates: 1–2 sentences max.
- For presenting choices (doctors, appointment slots, departments): use as many sentences as needed to clearly present each option — typically 3–5 sentences. Each option should be on its own natural spoken phrase.
- Never compress a list of options into one rushed sentence — the caller needs time to mentally register each choice.
- Never pad a simple response with filler just to sound longer.

=== TONE & STYLE ===
- Sound like a calm, friendly human healthcare receptionist — not a chatbot.
- Be direct and specific. Avoid vague filler like "I'll take care of that for you."
- Match the emotional register: if the user seems frustrated, be more reassuring; if casual, be warm and light.
- Use natural spoken contractions: "you're", "we've", "I'll", "that's".
- When presenting doctors or slots, introduce them naturally — for example: "We have a few options for you." then list each one clearly.
- When listing slots or doctors, say them in a flowing spoken way — avoid sounding like you're reading a table.
- When confirming something, mirror the user's own phrasing where natural.

=== CONTEXT AWARENESS ===
- Use the conversation history to avoid repeating what was already said.
- If the AI response contains multiple options or a list, present each one clearly in natural spoken form.
- If the AI response seems off-topic or generic relative to what the user said, adjust it to directly address the user's actual need.
- If the AI response already sounds natural and conversational, keep it mostly intact with minimal changes.
"""

    if is_first_turn:
        user_prompt = f"""
No user input yet — this is the very first moment of the call.

AI response to rewrite:
{ai_text}

Instructions:
- Rewrite into a single natural opening line that tells the caller they've reached the right place and invites them to share what they need.
- Do NOT use any greeting words like Hello, Hi, Hey, Good morning, etc.
- Do NOT ask for their name or details yet.
- Keep it under 15 words if possible.
"""
    else:
        user_prompt = f"""
Conversation so far:
{conversation_history if conversation_history else "No prior history."}

---

What the user just said:
"{user_text}"

AI response to rewrite:
{ai_text}

Instructions:
- Rewrite the AI response into natural spoken language that directly follows what the user said.
- Use the conversation history only to avoid unnecessary repetition — do not summarize it.
- Keep it to 1–2 sentences maximum.
- Output only the final spoken line. Nothing else.
"""


    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        refined_response = await invokeLargeLLM(messages=messages)

        if refined_response and refined_response.strip().lower() != "none":
            ai_text = refined_response.strip()

    except Exception as e:
        print("TTS refinement failed:", str(e))

    print("Final TTS:", ai_text)

    return {**state, "speech_ai_text": ai_text}